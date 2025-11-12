# src/learning_mcp/jobs_db.py
"""
SQLite ORM for ingest job tracking.

Purpose:
- Track enqueue/running/completed ingest jobs.
- Store provider/model info, progress counters (files/pages/chunks), errors, timestamps.
- Exposed via /ingest/jobs endpoints.

User question (example):
Q: "Where is the jobs DB stored?"
A:
    It's configured via the JOBS_DB_PATH environment variable.
    Example: JOBS_DB_PATH=/app/state/jobs.sqlite
"""

import os
import uuid
import sqlite3
from datetime import datetime
from enum import Enum
from typing import Optional, Dict, Any

# ---------- Config ----------
DB_PATH = os.getenv("JOBS_DB_PATH", "/app/state/jobs.sqlite")


class JobStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELED = "canceled"


class JobPhase(str, Enum):
    PREFLIGHT = "preflight"
    EXTRACT = "extract"
    EMBED = "embed"
    UPSERT = "upsert"
    FINISHED = "finished"


class JobsDB:
    def __init__(self, db_path: Optional[str] = None):
        self.db_path = db_path or DB_PATH
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        self._init_schema()

    def _connect(self):
        return sqlite3.connect(self.db_path)

    def _init_schema(self):
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS jobs (
                    job_id TEXT PRIMARY KEY,
                    profile TEXT,
                    provider TEXT,
                    model_name TEXT,
                    model_dim INTEGER,
                    vector_db TEXT,
                    collection TEXT,
                    truncate INTEGER,
                    status TEXT,
                    phase TEXT,
                    error TEXT,
                    files_total INTEGER,
                    files_done INTEGER,
                    pages_total INTEGER,
                    pages_done INTEGER,
                    chunks_done INTEGER,
                    current_file TEXT,
                    current_page INTEGER,
                    current_file_pages INTEGER,
                    chunks_per_min REAL,
                    created_at TEXT,
                    updated_at TEXT
                )
                """
            )

    # ---------- Job lifecycle ----------
    def start_job(
        self,
        profile: str,
        provider: str,
        model_name: str,
        model_dim: int,
        vector_db: str,
        collection: str,
        truncate: bool,
        files_total: int,
        pages_total: int,
        chunks_per_min: Optional[float] = None,   # NEW
    ) -> str:
        job_id = datetime.utcnow().strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:8]
        now = datetime.utcnow().isoformat()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO jobs (
                    job_id, profile, provider, model_name, model_dim,
                    vector_db, collection, truncate, status, phase,
                    files_total, files_done, pages_total, pages_done, chunks_done,
                    chunks_per_min, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    job_id,
                    profile,
                    provider,
                    model_name,
                    model_dim,
                    vector_db,
                    collection,
                    1 if truncate else 0,
                    JobStatus.QUEUED.value,
                    JobPhase.PREFLIGHT.value,
                    files_total,
                    0,
                    pages_total,
                    0,
                    0,
                    chunks_per_min,   # NEW
                    now,
                    now,
                ),
            )
        return job_id


    def mark_running(self, job_id: str):
        self._update(job_id, status=JobStatus.RUNNING.value)

    def set_phase(self, job_id: str, phase: JobPhase):
        self._update(job_id, phase=phase.value)

    def update_progress(self, job_id: str, **fields):
        self._update(job_id, **fields)

    def finish_job(self, job_id: str, status: JobStatus, error: Optional[str] = None):
        self._update(job_id, status=status.value, phase=JobPhase.FINISHED.value, error=error)

    def cancel_queued_or_running_for_profile(self, profile: str) -> int:
        with self._connect() as conn:
            cur = conn.execute(
                "UPDATE jobs SET status=?, updated_at=? WHERE profile=? AND status IN (?, ?)",
                (
                    JobStatus.CANCELED.value,
                    datetime.utcnow().isoformat(),
                    profile,
                    JobStatus.QUEUED.value,
                    JobStatus.RUNNING.value,
                ),
            )
            return cur.rowcount

    # ---------- Queries ----------
    def list_jobs(self, profile: Optional[str] = None, status: Optional[str] = None, limit: int = 20):
        query = "SELECT * FROM jobs WHERE 1=1"
        params = []
        
        if profile:
            query += " AND profile=?"
            params.append(profile)
        if status:
            query += " AND status=?"
            params.append(status)
        
        query += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)
        
        with self._connect() as conn:
            cur = conn.execute(query, tuple(params))
            cols = [c[0] for c in cur.description]
            return [dict(zip(cols, row)) for row in cur.fetchall()]

    def get_job(self, job_id: str) -> Optional[Dict[str, Any]]:
        with self._connect() as conn:
            cur = conn.execute("SELECT * FROM jobs WHERE job_id=?", (job_id,))
            row = cur.fetchone()
            if not row:
                return None
            cols = [c[0] for c in cur.description]
            return dict(zip(cols, row))


    # ---------- Internal ----------
    def _update(self, job_id: str, **fields):
        if not fields:
            return
        fields["updated_at"] = datetime.utcnow().isoformat()
        keys = ", ".join(f"{k}=?" for k in fields)
        values = list(fields.values()) + [job_id]
        with self._connect() as conn:
            conn.execute(f"UPDATE jobs SET {keys} WHERE job_id=?", values)
