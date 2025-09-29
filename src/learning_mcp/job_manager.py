# src/learning_mcp/job_manager.py
"""
Global registry for running ingest/embedding jobs.
"""


import asyncio
from typing import Dict

# job_id -> asyncio.Task
JOBS: Dict[str, asyncio.Task] = {}


def register_job(job_id: str, task: asyncio.Task) -> None:
    JOBS[job_id] = task


def pop_job(job_id: str):
    return JOBS.pop(job_id, None)


def get_job(job_id: str):
    return JOBS.get(job_id)


def all_jobs():
    return JOBS.copy()


def cancel_all():
    cancelled = []
    for job_id, task in list(JOBS.items()):
        if not task.done():
            task.cancel()
            cancelled.append(job_id)
        JOBS.pop(job_id, None)
    return cancelled
