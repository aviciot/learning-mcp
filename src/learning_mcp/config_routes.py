"""Config routes for profile management."""
import logging
from typing import Dict, Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from learning_mcp.config import settings

log = logging.getLogger("learning_mcp.config_routes")
router = APIRouter()


class ProfileResponse(BaseModel):
    profile: Dict[str, Any]


@router.get("/config/profile/{profile_name}", response_model=ProfileResponse, tags=["Config"])
async def get_profile_config(profile_name: str) -> ProfileResponse:
    """
    Get full configuration for a specific profile including autogen_hints.
    Used by AutoGen planner to load profile-specific templates and rules.
    """
    profiles = settings.load_profiles()
    profile = next(
        (p for p in profiles.get("profiles", []) if p.get("name") == profile_name),
        None
    )
    
    if not profile:
        raise HTTPException(
            status_code=404,
            detail=f"Profile '{profile_name}' not found in learning.yaml"
        )
    
    return ProfileResponse(profile=profile)
