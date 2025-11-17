"""Learning MCP V2.0 - FastAPI Job Management Server."""

import asyncio
import logging
import os
import uuid
import time
from datetime import datetime
from typing import Dict, List, Optional

from fastapi import FastAPI, HTTPException, Query, Body
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

# Configure logging to show all INFO level messages including AutoGen flow
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(name)s] %(levelname)s: %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

# Reuse existing infrastructure
from learning_mcp.config import settings, get_profile
from learning_mcp.embeddings import EmbeddingConfig, Embedder
from learning_mcp.vdb import VDB
from learning_mcp.jobs_db import JobsDB, JobStatus, JobPhase
from learning_mcp.document_loaders import (
    collect_chunks,
    known_document_count,
    estimate_pages_total,
)
from learning_mcp.search_routes import router as search_router
from learning_mcp.config_routes import router as config_router

log = logging.getLogger("learning_mcp.job_server")

# Initialize FastAPI
app = FastAPI(
    title="Learning MCP - Job Management",
    description="Background job tracking for document ingestion",
    version="2.0.0"
)

# CORS for web dashboards
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include search routes for AutoGen
app.include_router(search_router, prefix="", tags=["Search"])
app.include_router(config_router, prefix="", tags=["Config"])

# In-memory task registry (job_id -> asyncio.Task)
_RUNNING_TASKS: Dict[str, asyncio.Task] = {}


def _register_task(job_id: str, task: asyncio.Task) -> None:
    _RUNNING_TASKS[job_id] = task


def _pop_task(job_id: str) -> Optional[asyncio.Task]:
    return _RUNNING_TASKS.pop(job_id, None)


def _list_running_ids() -> List[str]:
    return [jid for jid, t in _RUNNING_TASKS.items() if not t.done()]


# ---------- Schemas ----------

class IngestRequest(BaseModel):
    profile: str = Field(..., example="dahua-camera")
    truncate: bool = Field(False, description="Clear collection before ingest")


class IngestResponse(BaseModel):
    job_id: str
    profile: str
    status: str
    message: str
    collection: Optional[str] = None
    canceled_previous: int = 0


class JobBrief(BaseModel):
    job_id: str
    profile: str
    status: str
    phase: str
    pages_done: int
    pages_total: int
    pct: int


class JobDetail(BaseModel):
    job_id: str
    profile: str
    status: str
    phase: str
    pages_done: int
    pages_total: int
    files_done: int
    files_total: int
    chunks_done: int
    error_msg: Optional[str]
    started_at: Optional[str]
    finished_at: Optional[str]


# ---------- Background Worker ----------

async def _worker_run_ingest(job_id: str, prof: dict, truncate: bool):
    """
    Background worker that loads, chunks, embeds, and upserts documents.
    Tracks progress in SQLite jobs_db.
    """
    db = JobsDB()
    profile_name = prof.get("name")
    
    try:
        # Setup
        ecfg = EmbeddingConfig.from_profile(prof)
        vcfg = prof.get("vectordb", {}) or {}
        cparams = prof.get("chunking", {}) or {}
        collection = vcfg.get("collection", profile_name)
        
        embedder = Embedder(ecfg)
        vdb = VDB(
            url=vcfg.get("url"),
            collection=collection,
            dim=ecfg.dim,
            distance=vcfg.get("distance", "cosine")
        )
        
        # Phase: LOAD
        db.set_phase(job_id, JobPhase.EXTRACT)
        log.info(f"Job {job_id}: Loading documents for profile '{profile_name}'")
        
        # Optionally truncate
        if truncate:
            log.info(f"Job {job_id}: Truncating collection '{collection}'")
            vdb.truncate()
        else:
            vdb.ensure_collection()
        
        # Load chunks
        chunks, stats = collect_chunks(
            prof,
            chunk_size=cparams.get("size", 1200),
            chunk_overlap=cparams.get("overlap", 200)
        )
        
        if not chunks:
            db.finish_job(job_id, status=JobStatus.COMPLETED, error="No chunks loaded")
            log.warning(f"Job {job_id}: No chunks to ingest")
            return
        
        db.update_progress(job_id, files_done=stats.get("files_done", 0))
        
        # Phase: EMBED
        db.set_phase(job_id, JobPhase.EMBED)
        log.info(f"Job {job_id}: Embedding {len(chunks)} chunks...")
        
        texts = [c["text"] for c in chunks]
        try:
            vectors = await embedder.embed(texts)
        except Exception as e:
            log.error(f"Job {job_id}: Embedding failed: {e}")
            db.finish_job(job_id, status=JobStatus.FAILED, error=str(e))
            return
        finally:
            await embedder.close()
        
        # Phase: UPSERT
        db.set_phase(job_id, JobPhase.UPSERT)
        log.info(f"Job {job_id}: Upserting {len(vectors)} vectors to Qdrant...")
        
        ids = []
        payloads = []
        for i, (chunk, vec) in enumerate(zip(chunks, vectors)):
            point_id = str(uuid.uuid5(
                uuid.NAMESPACE_DNS,
                f"{chunk['metadata'].get('doc_id')}|{chunk['metadata'].get('doc_path')}|{i}"
            ))
            ids.append(point_id)
            payloads.append({
                "text": chunk["text"],
                "doc_id": chunk["metadata"].get("doc_id"),
                "doc_path": chunk["metadata"].get("doc_path"),
                "chunk_idx": i,
                "profile": profile_name,
                "ingested_at": datetime.utcnow().isoformat()
            })
        
        vdb.upsert(vectors, payloads, ids)
        db.update_progress(job_id, chunks_done=len(ids))
        
        # Complete
        db.finish_job(job_id, status=JobStatus.COMPLETED)
        log.info(f"Job {job_id}: Completed successfully ({len(ids)} chunks)")
        
    except asyncio.CancelledError:
        log.warning(f"Job {job_id}: Cancelled by user")
        db.finish_job(job_id, status=JobStatus.CANCELED, error="Cancelled by user")
        raise
    except Exception as e:
        log.error(f"Job {job_id}: Failed with error: {e}")
        db.finish_job(job_id, status=JobStatus.FAILED, error=str(e))
    finally:
        _pop_task(job_id)


# ---------- Endpoints ----------

@app.post("/ingest/jobs", response_model=IngestResponse, tags=["Ingest"])
async def start_ingest_job(req: IngestRequest = Body(...)):
    """
    Start a background ingest job for a profile.
    
    Returns job_id immediately, job runs asynchronously.
    """
    profile_name = req.profile.strip()
    
    # Load profile
    profiles = settings.load_profiles()
    prof = next((p for p in profiles.get("profiles", []) if p.get("name") == profile_name), None)
    
    if not prof:
        raise HTTPException(status_code=404, detail=f"Profile '{profile_name}' not found")
    
    # Preflight checks
    files_total = known_document_count(prof)
    pages_total = estimate_pages_total(prof)
    
    if files_total == 0:
        raise HTTPException(status_code=400, detail=f"Profile '{profile_name}' has no documents to ingest")
    
    # Get metadata
    ecfg = EmbeddingConfig.from_profile(prof)
    vcfg = prof.get("vectordb", {}) or {}
    collection = vcfg.get("collection", profile_name)
    
    # Cancel any previous jobs for this profile
    db = JobsDB()
    canceled_prev = db.cancel_queued_or_running_for_profile(profile_name)
    
    # Create job record
    job_id = db.start_job(
        profile=profile_name,
        provider=(prof.get("embedding") or {}).get("backend", {}).get("primary", "unknown"),
        model_name=ecfg.ollama_model,
        model_dim=ecfg.dim,
        vector_db="qdrant",
        collection=collection,
        truncate=req.truncate,
        files_total=files_total,
        pages_total=pages_total,
    )
    
    # Start background worker
    task = asyncio.create_task(
        _worker_run_ingest(job_id, prof, req.truncate),
        name=f"ingest:{job_id}"
    )
    _register_task(job_id, task)
    
    log.info(f"Job {job_id}: Enqueued (profile={profile_name}, truncate={req.truncate}, canceled_previous={canceled_prev})")
    
    return IngestResponse(
        job_id=job_id,
        profile=profile_name,
        status=JobStatus.QUEUED,
        message=f"Ingest job started for profile '{profile_name}'",
        collection=collection,
        canceled_previous=canceled_prev
    )


@app.post("/ingest/cancel_all", tags=["Ingest"])
async def cancel_all_jobs():
    """
    Cancel all running ingest jobs.
    """
    db = JobsDB()
    running = _list_running_ids()
    
    log.warning(f"Cancelling all jobs: {running}")
    
    cancelled_ids = []
    
    # Issue cancellations
    for job_id in running:
        task = _RUNNING_TASKS.get(job_id)
        if task and not task.done():
            task.cancel()
    
    # Wait for tasks to handle cancellation
    await asyncio.sleep(0.1)
    
    # Collect results
    for job_id in running:
        task = _RUNNING_TASKS.get(job_id)
        if not task:
            continue
        
        try:
            await asyncio.wait_for(task, timeout=1.0)
        except asyncio.CancelledError:
            pass
        except asyncio.TimeoutError:
            log.warning(f"Job {job_id}: Timeout during cancellation")
        except Exception as e:
            log.error(f"Job {job_id}: Error during cancellation: {e}")
        finally:
            db.finish_job(job_id, status=JobStatus.CANCELED, error="Cancelled by user")
            cancelled_ids.append(job_id)
            _pop_task(job_id)
    
    log.warning(f"Cancelled {len(cancelled_ids)} jobs")
    
    return {
        "status": "ok",
        "cancelled_count": len(cancelled_ids),
        "jobs": cancelled_ids,
        "message": f"Cancelled {len(cancelled_ids)} running jobs"
    }


@app.get("/jobs", response_model=List[JobBrief], tags=["Jobs"])
async def list_jobs(
    profile: Optional[str] = Query(None, description="Filter by profile"),
    status: Optional[str] = Query(None, description="Filter by status"),
    limit: int = Query(20, ge=1, le=100)
):
    """
    List recent jobs with optional filters.
    """
    db = JobsDB()
    jobs = db.list_jobs(profile=profile, status=status, limit=limit)
    
    return [
        JobBrief(
            job_id=j["job_id"],
            profile=j["profile"],
            status=j["status"],
            phase=j["phase"],
            pages_done=j["pages_done"],
            pages_total=j["pages_total"],
            pct=j["pct"]
        )
        for j in jobs
    ]


@app.get("/jobs/{job_id}", response_model=JobDetail, tags=["Jobs"])
async def get_job_detail(job_id: str):
    """
    Get detailed status for a specific job.
    """
    db = JobsDB()
    job = db.get_job(job_id)
    
    if not job:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")
    
    return JobDetail(
        job_id=job["job_id"],
        profile=job["profile"],
        status=job["status"],
        phase=job["phase"],
        pages_done=job["pages_done"],
        pages_total=job["pages_total"],
        files_done=job["files_done"],
        files_total=job["files_total"],
        chunks_done=job.get("chunks_done", 0),
        error_msg=job.get("error"),
        started_at=job.get("created_at"),
        finished_at=job.get("updated_at")
    )


@app.get("/health", tags=["Health"])
async def health_check():
    """
    Health check endpoint.
    """
    return {
        "status": "ok",
        "service": "job-server",
        "version": "2.0.0",
        "running_jobs": len(_list_running_ids())
    }


if __name__ == "__main__":
    import uvicorn
    
    port = int(os.getenv("JOB_PORT", 8014))
    
    log.info(f"Starting Job Server on port {port}")
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=port,
        log_level="info"
    )
