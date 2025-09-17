from fastapi import APIRouter
from ..config import settings

router = APIRouter()

@router.get("/health")
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
