# src/learning_mcp/routes/jobs.py
"""
FastAPI routes: Monitor ingest jobs (list + detail).

Purpose:
- Provide lightweight monitoring for background ingest runs with page-centric progress and
  provider/model metadata.

User question (example):
Q: "How can I see recent runs and view a single job in detail?"
A:
    # List last 20
    Invoke-RestMethod -Uri "http://localhost:8013/ingest/jobs" -Method Get

    # Filter by profile
    Invoke-RestMethod -Uri "http://localhost:8013/ingest/jobs?profile=informatica-cloud" -Method Get

    # Filter by status
    Invoke-RestMethod -Uri "http://localhost:8013/ingest/jobs?status=running&limit=10" -Method Get

    # Detail by job_id
    Invoke-RestMethod -Uri "http://localhost:8013/ingest/jobs/20250919-142355-1a2b3c4d" -Method Get
"""

from __future__ import annotations
from typing import List, Optional

from fastapi import APIRouter, Query, HTTPException, Path
from pydantic import BaseModel, Field

from learning_mcp.jobs_db import JobsDB, JobStatus

router = APIRouter()


# ---------- Response models (Swagger-visible) ----------
# src/learning_mcp/routes/jobs.py

class JobBriefItem(BaseModel):
    job_id: str = Field(..., example="20250919-142355-1a2b3c4d")
    profile: str = Field(..., example="informatica-cloud")
    status: str = Field(..., example="running")
    phase: str = Field(..., example="embed")

    # page-centric progress
    pages_done: int = Field(..., example=120)
    pages_total: int = Field(..., example=340)
    pct: int = Field(..., example=35, description="round(100*pages_done/max(pages_total,1))")

    # secondary counters
    files_done: int = Field(..., example=1)
    files_total: int = Field(..., example=3)
    chunks_done: int = Field(..., example=910)

    # provider/model info
    provider: Optional[str] = Field(None, example="ollama")
    model_name: Optional[str] = Field(None, example="nomic-embed-text")
    model_dim: Optional[int] = Field(None, example=768)
    chunks_per_min: Optional[float] = Field(None, example=320.0)

    # timestamps
    updated_at: Optional[str] = Field(None, example="2025-09-19T14:25:30")

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "job_id": "20250919-142355-1a2b3c4d",
                    "profile": "informatica-cloud",
                    "status": "running",
                    "phase": "embed",
                    "pages_done": 120,
                    "pages_total": 340,
                    "pct": 35,
                    "files_done": 1,
                    "files_total": 3,
                    "chunks_done": 910,
                    "provider": "ollama",
                    "model_name": "nomic-embed-text",
                    "model_dim": 768,
                    "chunks_per_min": 320.0,
                    "updated_at": "2025-09-19T14:25:30"
                }
            ]
        }
    }



class JobDetailItem(BaseModel):
    job_id: str = Field(..., example="20250919-142355-1a2b3c4d")
    profile: str = Field(..., example="informatica-cloud")

    status: str = Field(..., example="running")
    phase: str = Field(..., example="embed")

    files_total: int = Field(..., example=3)
    files_done: int = Field(..., example=1)

    pages_total: int = Field(..., example=340)
    pages_done: int = Field(..., example=120)
    pct: int = Field(..., example=35, description="round(100*pages_done/max(pages_total,1))")

    chunks_done: int = Field(..., example=910)

    current_file: Optional[str] = Field(None, example="/app/data/iics/IICS_September2022_REST-API_Reference_en.pdf")
    current_page: Optional[int] = Field(None, example=17)
    current_file_pages: Optional[int] = Field(None, example=42)

    pages_per_min: Optional[float] = Field(None, example=58.4)
    chunks_per_min: Optional[float] = Field(None, example=320.0)
    eta_seconds: Optional[int] = Field(None, example=410)

    provider: Optional[str] = Field(None, example="ollama")
    model_name: Optional[str] = Field(None, example="nomic-embed-text")
    model_dim: Optional[int] = Field(None, example=768)

    vector_db: Optional[str] = Field(None, example="qdrant")
    collection: Optional[str] = Field(None, example="iics_docs")
    truncate: int = Field(..., example=1, description="1 if collection was dropped before ingest")

    created_at: str = Field(..., example="2025-09-19T14:23:55")
    started_at: Optional[str] = Field(None, example="2025-09-19T14:24:01")
    updated_at: Optional[str] = Field(None, example="2025-09-19T14:25:30")
    ended_at: Optional[str] = Field(None, example="2025-09-19T14:31:02")

    error: Optional[str] = Field(None, example=None)

    model_config = {
        "json_schema_extra": {
            "example": {
                "job_id": "20250919-142355-1a2b3c4d",
                "profile": "informatica-cloud",
                "status": "running",
                "phase": "embed",
                "files_total": 3,
                "files_done": 1,
                "pages_total": 340,
                "pages_done": 120,
                "pct": 35,
                "chunks_done": 910,
                "current_file": "/app/data/iics/IICS_September2022_REST-API_Reference_en.pdf",
                "current_page": 17,
                "current_file_pages": 42,
                "pages_per_min": 58.4,
                "chunks_per_min": 320.0,
                "eta_seconds": 410,
                "provider": "ollama",
                "model_name": "nomic-embed-text",
                "model_dim": 768,
                "vector_db": "qdrant",
                "collection": "iics_docs",
                "truncate": 1,
                "created_at": "2025-09-19T14:23:55",
                "started_at": "2025-09-19T14:24:01",
                "updated_at": "2025-09-19T14:25:30",
                "ended_at": None,
                "error": None
            }
        }
    }


# ---------- List endpoint ----------

@router.get(
    "/ingest/jobs",
    tags=["monitoring"],
    summary="List recent ingest jobs",
    description=(
        "Returns the last N ingest runs with page-centric progress. "
        "Optional filters by profile and status.\n\n"
        "**Examples:**\n"
        "- `GET /ingest/jobs`\n"
        "- `GET /ingest/jobs?profile=informatica-cloud`\n"
        "- `GET /ingest/jobs?status=running&limit=10`\n"
    ),
    response_model=List[JobBriefItem],
)
async def list_jobs(
    limit: int = Query(20, ge=1, le=200, description="Max jobs to return"),
    profile: Optional[str] = Query(None, description="Filter by profile name"),
    status: Optional[str] = Query(
        None,
        description=f"Filter by status ({', '.join([JobStatus.QUEUED, JobStatus.RUNNING, JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELED])})",
    ),
) -> List[JobBriefItem]:
    db = JobsDB()
    rows = db.list_jobs(limit=limit, profile=profile, status=status)
    out: List[JobBriefItem] = []
    for r in rows:
        denom = max(r.pages_total, 1)
        out.append(
            JobBriefItem(
                job_id=r.job_id,
                profile=r.profile,
                status=r.status,
                phase=r.phase,
                pages_done=r.pages_done,
                pages_total=r.pages_total,
                pct=round(100 * r.pages_done / denom),
                files_done=r.files_done,
                files_total=r.files_total,
                chunks_done=r.chunks_done,
                updated_at=r.updated_at,
                provider=getattr(r, "provider", None),
                model_name=getattr(r, "model_name", None),
                model_dim=getattr(r, "model_dim", None),
                chunks_per_min=getattr(r, "chunks_per_min", None),
            )
        )
    return out


# ---------- Detail endpoint ----------

@router.get(
    "/ingest/jobs/{job_id}",
    tags=["monitoring"],
    summary="Get a single ingest job (detail)",
    description=(
        "Returns a single ingest run with full metadata, current file/page, and progress.\n\n"
        "**Example:** `GET /ingest/jobs/20250919-142355-1a2b3c4d`"
    ),
    response_model=JobDetailItem,
)
async def get_job(
    job_id: str = Path(..., description="Job identifier as returned by enqueue/start endpoints",
                       example="20250919-142355-1a2b3c4d")
) -> JobDetailItem:
    db = JobsDB()
    j = db.get_job(job_id)
    if not j:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found")

    pages_total = j.pages_total or 0
    pages_done = j.pages_done or 0
    pct = round(100 * pages_done / max(pages_total, 1))

    return JobDetailItem(
        job_id=j.job_id,
        profile=j.profile,
        status=j.status,
        phase=j.phase,
        files_total=j.files_total or 0,
        files_done=j.files_done or 0,
        pages_total=pages_total,
        pages_done=pages_done,
        pct=pct,
        chunks_done=j.chunks_done or 0,
        current_file=j.current_file,
        current_page=j.current_page,
        current_file_pages=j.current_file_pages,
        pages_per_min=j.pages_per_min,
        chunks_per_min=j.chunks_per_min,
        eta_seconds=j.eta_seconds,
        provider=j.provider,
        model_name=j.model_name,
        model_dim=j.model_dim,
        vector_db=j.vector_db,
        collection=j.collection,
        truncate=j.truncate or 0,
        created_at=j.created_at,
        started_at=j.started_at,
        updated_at=j.updated_at,
        ended_at=j.ended_at,
        error=j.error,
    )


# ---------- Last N runs endpoint (lightweight) ----------


@router.get(
    "/ingest/last-runs",
    tags=["monitoring"],
    summary="Last N runs (default 3)",
    response_model=List[JobBriefItem],  operation_id="ingest_last_runs"
)
async def last_runs(
    limit: int = Query(3, ge=1, le=50, description="Max jobs to return (default 3)")
) -> List[JobBriefItem]:
    """
    Return the most recent runs with lightweight page-centric progress.
    """
    db = JobsDB()
    rows = db.list_jobs(limit=limit)  # returns list[dict] in current JobsDB
    out: List[JobBriefItem] = []
    for r in rows:
        pages_total = int(r.get("pages_total") or 0)
        pages_done = int(r.get("pages_done") or 0)
        denom = max(pages_total, 1)
        out.append(
            JobBriefItem(
                job_id=r.get("job_id", ""),
                profile=r.get("profile", ""),
                status=r.get("status", ""),
                phase=r.get("phase", ""),
                pages_done=pages_done,
                pages_total=pages_total,
                pct=round(100 * pages_done / denom),
                files_done=int(r.get("files_done") or 0),
                files_total=int(r.get("files_total") or 0),
                chunks_done=int(r.get("chunks_done") or 0),
                provider=r.get("provider"),
                model_name=r.get("model_name"),
                model_dim=r.get("model_dim"),
                chunks_per_min=r.get("chunks_per_min"),
                updated_at=r.get("updated_at"),             
            )
        )
    return out