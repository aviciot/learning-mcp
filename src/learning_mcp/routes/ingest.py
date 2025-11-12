# /app/src/learning_mcp/routes/ingest.py
"""
FastAPI routes: Enqueue + cancel ingest jobs (with SQLite tracking).

Purpose:
- POST /ingest/jobs        : enqueue background ingest for a profile (tracks the asyncio.Task by job_id)
- POST /ingest/cancel_all  : cancel all running/queued ingests (kills Ollama/Cloudflare embedding via task cancel)
- Background worker        : extracts, chunks, embeds, upserts; updates progress in SQLite

Notes:
- Type-agnostic ingest via loader registry (PDF/JSON and future types).
- Deterministic IDs for upserts (UUIDv5) to keep re-ingest idempotent and Qdrant-compliant.
"""

from __future__ import annotations
from typing import Optional, List, Dict, Any
import os, time, logging, asyncio
import hashlib
import uuid  # <-- NEW

from fastapi import APIRouter, Body, HTTPException
from pydantic import BaseModel, Field

from learning_mcp.config import settings
from learning_mcp.embeddings import EmbeddingConfig, Embedder, EmbeddingError
from learning_mcp.vdb import VDB
from learning_mcp.jobs_db import JobsDB, JobStatus, JobPhase

# type-agnostic document loaders
from learning_mcp.document_loaders import (
    collect_chunks,
    known_document_count,
    estimate_pages_total,
)

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
    cparams = profile.get("chunking", {}) or {}
    chunk_size = int(cparams.get("size", 1200))
    chunk_overlap = int(cparams.get("overlap", 200))
    log.info(
        "job.plan id=%s backend_primary=%s model=%s cf_model=%s dim=%s chunk_size=%s overlap=%s concurrency=%s",
        job_id,
        backend_primary,
        ecfg.ollama_model,
        cf_model or "",
        ecfg.dim,
        chunk_size,
        chunk_overlap,
        os.getenv("EMBED_CONCURRENCY", ""),
    )

    # ensure collection
    if truncate:
        log.info("job.vdb.truncate id=%s collection=%s", job_id, collection)
        vdb.truncate()
    else:
        vdb.ensure_collection()

    db.mark_running(job_id)
    db.set_phase(job_id, JobPhase.PREFLIGHT)

    # Collect chunks (type-agnostic) and preflight stats
    chunks, stats = collect_chunks(profile, chunk_size=chunk_size, chunk_overlap=chunk_overlap)
    files_total = int(stats.get("files_total", 0))
    pages_total = int(stats.get("pages_total", 0))
    db.update_progress(job_id, files_total=files_total, pages_total=pages_total, files_done=0, pages_done=0, chunks_done=0)
    log.info("job.preflight id=%s files=%s pages=%s", job_id, files_total, pages_total)

    # Nothing to ingest
    if files_total == 0 or not chunks:
        db.finish_job(job_id, status=JobStatus.COMPLETED)
        log.warning("job.done id=%s status=completed (no chunks)", job_id)
        await emb.close()
        _pop_task(job_id)
        return

    try:
        # ---------- EMBED ----------
        db.set_phase(job_id, JobPhase.EMBED)
        doc_id = str(profile.get("name") or "profile")
        texts = [c.get("text", "") for c in chunks]
        log.info("job.embed.start id=%s chunks=%s", job_id, len(texts))

        t0 = time.perf_counter()
        try:
            # Embed IDs for cache alignment (stable but not necessarily the final point IDs)
            embed_ids = [f"{doc_id}:{i}" for i in range(len(texts))]
            vecs = await emb.embed(texts, ids=embed_ids)
        except asyncio.CancelledError:
            log.warning("job.cancelled id=%s phase=embed", job_id)
            db.finish_job(job_id, status=JobStatus.CANCELED, error="cancelled by user")
            raise
        except EmbeddingError as e:
            db.finish_job(job_id, status=JobStatus.FAILED, error=f"Embedding failed: {e}")
            log.error("job.embed.fail id=%s err=%s", job_id, e)
            return
        t1 = time.perf_counter()

        # ---------- UPSERT ----------
        db.set_phase(job_id, JobPhase.UPSERT)

        payloads: List[Dict[str, Any]] = []
        ids: List[str] = []  # <-- valid UUIDs for Qdrant

        for i, ch in enumerate(chunks):
            meta = ch.get("metadata") or {}

            # Deterministic seed for UUIDv5
            stable = f"{doc_id}|{meta.get('path','')}|{i}"
            pid_uuid = str(uuid.uuid5(uuid.NAMESPACE_DNS, stable))  # valid UUID string

            # Optional: keep a short hash for human-readable debugging (not used as ID)
            short_hash = hashlib.sha256(stable.encode("utf-8", errors="ignore")).hexdigest()[:32]

            payload = {
                "hash": short_hash,                  # for debugging/trace, NOT used as point ID
                "doc_id": doc_id,                    # retriever filter
                "chunk_id": f"{doc_id}:{meta.get('source','doc')}:{i}",
                "profile": doc_id,
                "doc_path": meta.get("doc_path") or meta.get("source") or "",
                "chunk_idx": i,
                "text": ch.get("text", ""),
            }
            # Pass-through useful metadata for retrieval/formatting
            for k in ("section", "title", "source", "source_id", "path", "page_start", "page_end"):
                if meta.get(k) is not None:
                    payload[k] = meta.get(k)

            payloads.append(payload)
            ids.append(pid_uuid)  # <-- use deterministic UUIDv5

        # Pass explicit UUIDs to Qdrant (compliant & idempotent)
        vdb.upsert(vectors=vecs, payloads=payloads, ids=ids)
        try:
            log.info("job.upsert.ok id=%s total_points=%s", job_id, vdb.count())
        except Exception:
            pass

        chunks_done = len(chunks)
        chunks_per_min = (chunks_done / max(t1 - t0, 1e-6)) * 60.0
        db.update_progress(job_id, files_done=files_total, pages_done=pages_total,
                           chunks_done=chunks_done, chunks_per_min=chunks_per_min)
        log.info("job.done.metrics id=%s chunks=%s cpm=%.1f", job_id, chunks_done, chunks_per_min)

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

    # Preflight counts without heavy loading (type-agnostic)
    files_total = known_document_count(prof)
    pages_total = estimate_pages_total(prof)
    if files_total == 0:
        raise HTTPException(status_code=400, detail=f"Profile '{profile_name}' has no documents to ingest")

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
