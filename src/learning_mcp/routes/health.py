from fastapi import APIRouter

from ..config import settings

router = APIRouter()


@router.get("/health")
def health():
    """Return basic service info.

    Call `GET /health` to verify the API is up. The response lists the
    active environment, server port, and the profile names discovered in
    `config/learning.yaml`, making it useful as a quick readiness probe.
    """
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
