# /src/learning_mcp/routes/config_route.py
"""
Configuration & profile diagnostics.
Purpose: Inspect profiles from config/learning.yaml and see resolved embedding/vector DB settings.

User question: "How can I view available profiles and the resolved config for one profile?"

Example (PowerShell):
  # List all profiles
  Invoke-RestMethod -Uri http://localhost:8013/config/profiles -Method Get

  # Inspect one profile
  Invoke-RestMethod -Uri http://localhost:8013/config/profile/dahua-camera -Method Get
"""

from __future__ import annotations
from typing import Dict, Any

from fastapi import APIRouter, HTTPException

from learning_mcp.config import settings
from learning_mcp.embeddings import EmbeddingConfig

router = APIRouter(prefix="/config", tags=["config"])


@router.get(
    "/profiles",
    summary="List profiles",
    description="Returns profile names discovered in **config/learning.yaml**.",
)
def list_profiles():
    profs = settings.load_profiles()
    names = [p.get("name") for p in profs.get("profiles", [])]
    return {"profiles": names}


@router.get(
    "/profile/{name}",
    summary="Inspect a single profile",
    description=(
        "Returns the raw profile plus resolved embedding and vector DB configuration. "
        "Also surfaces autogen hints for planner/critic prompts."
    ),
)
def inspect_profile(name: str):
    profs = settings.load_profiles()
    prof = next((p for p in profs.get("profiles", []) if p.get("name") == name), None)
    if not prof:
        raise HTTPException(
            status_code=404,
            detail=f"Profile '{name}' not found in {settings.PROFILES_PATH}",
        )

    # Resolve embedding config (primary/fallback/dim + credentials/hosts)
    ecfg = EmbeddingConfig.from_profile(prof)

    # Vector DB config (optional in YAML)
    vcfg = prof.get("vectordb", {}) or {}
    url = vcfg.get("url")
    col = (vcfg.get("collections") or {}).get("docs", "docs_default")
    distance = (vcfg.get("distance") or "cosine").lower()

    # Autogen hints (if present in YAML)
    autogen_hints = prof.get("autogen_hints") or {}

    # Health snapshot (no network call; we don't create VDB or query here)
    snapshot: Dict[str, Any] = {
        "embedding": {
            "primary": ecfg.primary,
            "fallback": ecfg.fallback,
            "dim": ecfg.dim,
            "cloudflare": {
                "account_id": bool(ecfg.cf_account_id),
                "model": ecfg.cf_model,
                "has_api_token": bool(ecfg.cf_api_token),
            },
            "ollama": {
                "host": ecfg.ollama_host,
                "model": ecfg.ollama_model,
            },
        },
        "vectordb": {
            "url": url,
            "collection": col,
            "distance": distance,
        },
        # Surface autogen hints in the resolved section for convenience.
        "autogen_hints": autogen_hints,
    }

    # Return both the raw profile (verbatim from YAML) and the resolved snapshot
    return {"profile": prof, "resolved": snapshot}
