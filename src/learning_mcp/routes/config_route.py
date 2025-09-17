from fastapi import APIRouter
from ..config import settings


router = APIRouter()

@router.get("/config")
def get_config():
    profiles = settings.load_profiles()
    names = [p.get("name") for p in profiles.get("profiles", [])]
    return {
        "status": "ok",
        "profiles": names,
        "profiles_raw_present": bool(profiles),
        "env": settings.ENV,
        "port": settings.PORT,
    }
