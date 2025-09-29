# /src/learning_mcp/routes/health.py
"""
Basic health/readiness endpoint.
Purpose: Verify API is up, show env/port, and list profiles from config/learning.yaml.

User question: "How do I quickly check the service is running and which profiles are loaded?"

Example (PowerShell):
  Invoke-RestMethod -Uri http://localhost:8013/health -Method Get
"""

from fastapi import APIRouter
from learning_mcp.config import settings

router = APIRouter()


@router.get(
    "/health",
    tags=["health"],
    summary="Service health",
    description="Returns status, environment, port, version, and available profile names from config.",
)
def health():
    profiles = settings.load_profiles()
    names = [p.get("name") for p in profiles.get("profiles", [])]
    return {
        "status": "ok",
        "service": "learning-mcp",
        "env": settings.ENV,
        "port": settings.PORT,
        "profiles": names,
        "version": "0.1.0",
    }
