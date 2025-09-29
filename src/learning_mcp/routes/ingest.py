# /app/src/learning_mcp/routes/ingest.py
"""
FastAPI routes: Enqueue + cancel ingest jobs (with SQLite tracking).

Purpose:
- POST /ingest/jobs        : enqueue background ingest for a profile (tracks the asyncio.Task by job_id)
- POST /ingest/cancel_all  : cancel all running/queued ingests (kills Ollama/Cloudflare embedding via task cancel)
- Background worker        : extracts, chunks, embeds, upserts; updates progress in SQLite

User question (example):
Q: "How do I start an ingest and, if needed, cancel all running ingests?"
A:
  # Enqueue (Swagger example body is prefilled)
  Invoke-RestMethod -Uri http://localhost:8013/ingest/jobs -Method Post -ContentType 'application/json' `
    -Body '{"profile":"dahua-camera","truncate":true}'

  # Cancel all
  Invoke-RestMethod -Uri http://localhost:8013/ingest/cancel_all -Method Post
"""
from __future__ import annotations
from typing import Optional, List, Dict, Any
import os, time, logging, asyncio

import uuid
from fastapi import APIRouter, Body, HTTPException
from pydantic import BaseModel, Field

from learning_mcp.config import settings
from learning_mcp.embeddings import EmbeddingConfig, Embedder, EmbeddingError
from learning_mcp.vdb import VDB
from learning_mcp.pdf_loader import load_pdf
from learning_mcp.page_ranges import compute_pages
from learning_mcp.jobs_db import JobsDB, JobStatus, JobPhase

# prefer pypdf if available (faster), fallback to PyPDF2
try:
    from pypdf import PdfReader  # type: ignore
except Exception:
    from PyPDF2 import PdfReader  # type: ignore

router = APIRouter()
log = logging.getLogger("learning_mcp.ingest")

# ---------------- In-memory task registry (job_id -> asyncio.Task) ----------------
_RUNNING_TASKS: Dict[str, asyncio.Task] = {}

def _register_task(job_id: str, task: asyncio.Task) -> None:
    _RUNNING_TASKS[job_id] = task

def _pop_task(job_id: str) -> Optional[asyncio.Task]:
    return _RUNNING_TASKS.pop(job_id, None)

def _list_running_ids() -> List[str]:
    return [jid for jid, t in _RUNNING_TASKS.items() if not t.done()]

# ---------- Schemas ----------
class EnqueueIngestRequest(BaseModel):
    profile: str = Field(..., description="Profile name from config/learning.yaml")
    truncate: bool = Field(False, description="Drop & recreate the target collection before ingest")
    model_config = {"json_schema_extra": {"example": {"profile": "dahua-camera", "truncate": True}}}

class EnqueueIngestResponse(BaseModel):
    status: str = Field(..., example="queued")
    job_id: str = Field(..., example="20250919-142355-1a2b3c4d")
    profile: str = Field(..., example="dahua-camera")
    canceled_previous: int = Field(..., example=1)
    collection: str = Field(..., example="docs_dahua")

# ---------- Helpers ----------
def _profile_docs(profile: Dict[str, Any]) -> List[Dict[str, Any]]:
    return [d for d in (profile.get("documents") or []) if (d.get("type") or "").lower() == "pdf"]

def _count_selected_pages(pdf_path: str, include_spec: Optional[str], exclude_spec: Optional[str]) -> int:
    reader = PdfReader(pdf_path)
    total = len(reader.pages)
    pages = compute_pages(include_spec=include_spec, exclude_spec=exclude_spec, total_pages=total)
    return len(pages)

# ---------- Worker ----------
async def _worker_run_ingest(job_id: str, profile: Dict[str, Any], truncate: bool) -> None:
    db = JobsDB()
    log.info("job.start id=%s profile=%s truncate=%s", job_id, profile.get("name"), truncate)

    vcfg = profile.get("vectordb", {}) or {}
    collection: str = vcfg.get("collection")
    ecfg = EmbeddingConfig.from_profile(profile)
    emb = Embedder(ecfg)
    vdb = VDB(url=vcfg.get("url"), collection=collection, dim=ecfg.dim, distance=(vcfg.get("distance") or "cosine"))

    # plan logging
    backend_primary = (profile.get("embedding", {}) or {}).get("backend", {}).get("primary", "ollama")
    cf_model = (profile.get("embedding", {}) or {}).get("cloudflare", {}).get("model")
    log.info(
        "job.plan id=%s backend_primary=%s model=%s cf_model=%s dim=%s chunk_size=%s overlap=%s concurrency=%s",
        job_id,
        backend_primary,
        ecfg.ollama_model,
        cf_model or "",
        ecfg.dim,
        (profile.get("chunking") or {}).get("size", 1200),
        (profile.get("chunking") or {}).get("overlap", 200),
        os.getenv("EMBED_CONCURRENCY", ""),
    )

    # ensure collection
    if truncate:
        log.info("job.vdb.truncate id=%s collection=%s", job_id, collection)
        vdb.truncate()
    else:
        vdb.ensure_collection()

    cparams = profile.get("chunking", {}) or {}
    chunk_size = int(cparams.get("size", 1200))
    chunk_overlap = int(cparams.get("overlap", 200))

    db.mark_running(job_id)
    db.set_phase(job_id, JobPhase.PREFLIGHT)

    pdfs = _profile_docs(profile)
    files_total = len(pdfs)
    pages_total = sum(
        _count_selected_pages(
            (d.get("path") or "").strip(),
            include_spec=(d.get("include_pages") or profile.get("include_pages")),
            exclude_spec=(d.get("exclude_pages") or profile.get("exclude_pages")),
        )
        for d in pdfs
        if d.get("path") and os.path.exists(d.get("path"))
    )
    db.update_progress(job_id, files_total=files_total, pages_total=pages_total, files_done=0, pages_done=0, chunks_done=0)
    log.info("job.preflight id=%s files=%s pages=%s", job_id, files_total, pages_total)

    pages_done = files_done = chunks_done = 0

    try:
        for d in pdfs:
            # cooperative cancel point
            await asyncio.sleep(0)
            path = (d.get("path") or "").strip()
            if not path or not os.path.exists(path):
                log.warning("job.skip id=%s missing_file=%s", job_id, path)
                continue

            db.set_phase(job_id, JobPhase.EXTRACT)
            reader = PdfReader(path)
            sel_pages = compute_pages(
                include_spec=(d.get("include_pages") or profile.get("include_pages")),
                exclude_spec=(d.get("exclude_pages") or profile.get("exclude_pages")),
                total_pages=len(reader.pages),
            )
            current_file_pages = len(sel_pages)
            db.update_progress(job_id, current_file=path, current_page=0, current_file_pages=current_file_pages)
            log.info("job.extract id=%s file=%s pages_selected=%s", job_id, os.path.basename(path), current_file_pages)

            chunks = load_pdf(
                path,
                include_pages=(d.get("include_pages") or profile.get("include_pages")),
                exclude_pages=(d.get("exclude_pages") or profile.get("exclude_pages")),
                chunk_size=chunk_size,
                chunk_overlap=chunk_overlap,
            )

            pages_done += current_file_pages
            db.update_progress(job_id, pages_done=pages_done, current_page=current_file_pages)

            if not chunks:
                files_done += 1
                db.update_progress(job_id, files_done=files_done)
                log.info("job.nochunks id=%s file=%s", job_id, os.path.basename(path))
                continue
            doc_id = profile.get("name") 
            
            # EMBED
            db.set_phase(job_id, JobPhase.EMBED)
            log.info("job.embed.start id=%s file=%s chunks=%s", job_id, os.path.basename(path), len(chunks))
            t0 = time.perf_counter()
            try:
                doc_id = profile.get("name")   # canonical document id, e.g., "dahua-camera"
                ids = [f"{doc_id}:{os.path.basename(path)}:{i}" for i in range(len(chunks))]
                vecs = await emb.embed(chunks, ids=ids)  # optional cache hook supported
            except asyncio.CancelledError:
                log.warning("job.cancelled id=%s phase=embed", job_id)
                db.finish_job(job_id, status=JobStatus.CANCELED, error="cancelled by user")
                raise
            except EmbeddingError as e:
                db.finish_job(job_id, status=JobStatus.FAILED, error=f"Embedding failed: {e}")
                log.error("job.embed.fail id=%s err=%s", job_id, e)
                return
            t1 = time.perf_counter()

            # UPSERT
            db.set_phase(job_id, JobPhase.UPSERT)
            ids = [str(uuid.uuid4()) for _ in range(len(chunks))]  # ✅ valid point IDs for Qdrant

            payloads = []
            for i in range(len(chunks)):
                payloads.append({
                    "doc_id": doc_id,   # align with retriever filter
                    "chunk_id": f"{doc_id}:{os.path.basename(path)}:{i}",  # your readable ID lives here
                    "profile": profile.get("name"),
                    "doc_path": path,
                    "chunk_idx": i,
                    "text": chunks[i],
                })
            vdb.upsert(vectors=vecs, payloads=payloads, ids=ids)
            try:
                log.info("job.upsert.ok id=%s total_points=%s", job_id, vdb.count())
            except Exception:
                pass
            chunks_done += len(chunks)
            chunks_per_min = (len(chunks) / max(t1 - t0, 1e-6)) * 60.0
            files_done += 1
            db.update_progress(job_id, files_done=files_done, chunks_done=chunks_done, chunks_per_min=chunks_per_min)
            log.info("job.file.done id=%s file=%s chunks=%s total_chunks=%s cpm=%.1f",
                     job_id, os.path.basename(path), len(chunks), chunks_done, chunks_per_min)

        db.finish_job(job_id, status=JobStatus.COMPLETED)
        log.info("job.done id=%s status=completed", job_id)
    finally:
        await emb.close()
        _pop_task(job_id)  # cleanup from registry

# ---------- Endpoints ----------
@router.post(
    "/ingest/jobs",
    tags=["ingest"],
    summary="Enqueue a background ingest job",
    response_model=EnqueueIngestResponse,
)
async def enqueue_ingest(
    body: EnqueueIngestRequest = Body(..., example={"profile": "dahua-camera", "truncate": True}),
) -> EnqueueIngestResponse:
    profile_name = body.profile.strip()
    profiles = settings.load_profiles()
    prof = next((p for p in profiles.get("profiles", []) if p.get("name") == profile_name), None)
    if not prof:
        raise HTTPException(status_code=404, detail=f"Profile '{profile_name}' not found")

    pdfs = _profile_docs(prof)
    if not pdfs:
        raise HTTPException(status_code=400, detail=f"Profile '{profile_name}' has no PDF documents")

    # Embedding/VDB meta for logging
    ecfg = EmbeddingConfig.from_profile(prof)
    vcfg = prof.get("vectordb", {}) or {}
    collection: str = vcfg.get("collection")
    log.info(
        "enqueue plan profile=%s provider=%s model=%s dim=%s collection=%s",
        profile_name,
        (prof.get("embedding") or {}).get("backend", {}).get("primary", "ollama"),
        ecfg.ollama_model,
        ecfg.dim,
        collection,
    )
    

    # Preflight totals
    files_total = len(pdfs)
    pages_total = sum(
        _count_selected_pages(
            (d.get("path") or "").strip(),
            include_spec=(d.get("include_pages") or prof.get("include_pages")),
            exclude_spec=(d.get("exclude_pages") or prof.get("exclude_pages")),
        )
        for d in pdfs
        if d.get("path") and os.path.exists(d.get("path"))
    )

    db = JobsDB()
    canceled_prev = db.cancel_queued_or_running_for_profile(profile_name)
    
    job_id = db.start_job(
        profile=profile_name,
        provider=(prof.get("embedding") or {}).get("backend", {}).get("primary", "unknown"),
        model_name=ecfg.ollama_model,
        model_dim=ecfg.dim,
        vector_db="qdrant",
        collection=collection,
        truncate=bool(body.truncate),
        files_total=files_total,
        pages_total=pages_total,
    )

    # Start worker task explicitly so we can cancel it later
    task = asyncio.create_task(_worker_run_ingest(job_id, prof, bool(body.truncate)), name=f"ingest:{job_id}")
    _register_task(job_id, task)

    log.info("Job %s: enqueued (profile=%s, truncate=%s, canceled_previous=%s)", job_id, profile_name, body.truncate, canceled_prev)
    return EnqueueIngestResponse(
        status=JobStatus.QUEUED,
        job_id=job_id,
        profile=profile_name,
        canceled_previous=canceled_prev,
        collection=collection,
    )

@router.post(
    "/ingest/cancel_all",
    tags=["ingest"],
    summary="Cancel all running ingest jobs",
    description="Cancels all tracked asyncio tasks and marks corresponding jobs as 'canceled' in the DB.",
)
async def cancel_all_ingest():
    db = JobsDB()
    running = _list_running_ids()
    log.warning("cancel_all.start running_jobs=%s", running)

    cancelled_ids: List[str] = []
    # Issue cancellations
    for job_id in running:
        t = _RUNNING_TASKS.get(job_id)
        if t and not t.done():
            t.cancel()

    # Give tasks a moment to handle CancelledError cooperatively
    await asyncio.sleep(0.05)

    # Collect results and update DB
    for job_id in running:
        t = _RUNNING_TASKS.get(job_id)
        if not t:
            continue
        try:
            await asyncio.wait_for(t, timeout=1.0)
        except asyncio.CancelledError:
            pass
        except asyncio.TimeoutError:
            # still running; mark intent and leave task to finish/exit soon
            log.warning("cancel_all.timeout job_id=%s still-stopping", job_id)
        except Exception as e:
            log.error("cancel_all.task_error job_id=%s err=%s", job_id, e)
        finally:
            # Mark job canceled in DB (idempotent even if worker already did it)
            db.finish_job(job_id, status=JobStatus.CANCELED, error="cancelled by user")
            cancelled_ids.append(job_id)
            _pop_task(job_id)

    log.warning("cancel_all.done cancelled=%s", cancelled_ids)
    return {"status": "cancelled", "jobs": cancelled_ids}
