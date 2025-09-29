# /app/src/learning_mcp/routes/api_agent.py
"""
API Agent: cache → retriever → AutoGen fallback

Purpose
-------
Handles API-related user queries:
  1) Check in-memory TTL cache.
  2) On miss, call /search/api_context over HTTP.
  3) If a usable endpoint is found, return plan and cache it.
  4) Otherwise, hand off to AutoGen (if enabled).

User example
------------
POST /agent/api
{
  "q": "wifi settings",
  "profile": "dahua-camera",
  "top_k": 5
}
"""
import os
import uuid
import json
import logging
import httpx
from typing import Optional, Dict, Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

# <-- IMPORTANT: import plan_with_autogen from the top-level module (not routes)
from learning_mcp.autogen_agent import plan_with_autogen

# ---------- Router ----------
router = APIRouter(prefix="/agent", tags=["api_agent"])
log = logging.getLogger("api_agent")
log.setLevel(logging.INFO)

# ---------- Config ----------
DEFAULT_PROFILE = "dahua-camera"
DEFAULT_TOP_K = 5
USE_AUTOGEN = os.getenv("USE_AUTOGEN", "0") == "1"
API_AGENT_BASE = os.getenv("API_AGENT_BASE_URL", "http://localhost:8013").rstrip("/")

# ---------- Simple in-memory cache (TTL / eviction not implemented here) ----------
class TTLCache:
    def __init__(self):
        self._cache: Dict[str, Dict[str, Any]] = {}
    def get(self, k: str):
        return self._cache.get(k)
    def set(self, k: str, v: Dict[str, Any]):
        self._cache[k] = v

_CACHE = TTLCache()

# ---------- Schemas ----------
class Plan(BaseModel):
    endpoint: str
    method: str
    params: Dict[str, Any]
    provenance: Optional[Dict[str, Any]] = None

class ApiAgentRequest(BaseModel):
    q: str = Field(..., description="Natural language question")
    profile: Optional[str] = Field(None, description="Profile name (from learning.yaml)")
    top_k: Optional[int] = Field(DEFAULT_TOP_K, description="Retriever top_k")

class ApiAgentResponse(BaseModel):
    request_id: str
    status: str
    source: Optional[str] = None
    plan: Optional[Plan] = None
    reason: Optional[str] = None
    error: Optional[str] = None
    raw: Optional[Dict[str, Any]] = None

# ---------- Helpers ----------
async def _call_api_context(q: str, profile: str, top_k: int):
    url = f"{API_AGENT_BASE}/search/api_context"
    async with httpx.AsyncClient(timeout=20) as client:
        r = await client.post(url, json={"q": q, "profile": profile, "top_k": top_k, "read_only": True})
        r.raise_for_status()
        return r.json()

def _extract_plan(results: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Best-effort plan extraction from api_context hits.
    Returns first usable plan dict or None.
    """
    for hit in results.get("results", []):
        hints = hit.get("hints") or {}
        urls = hints.get("url_candidates") or []
        if not urls:
            continue
        return {
            "endpoint": urls[0],
            "method": (hints.get("method_hint") or "GET"),
            "params": hints.get("query_candidates") or {},
            "provenance": {"top_hit": hit},
        }
    return None

# ---------- Endpoint ----------
@router.post(
    "/api",
    response_model=ApiAgentResponse,
    summary="API Agent: cache → retriever → AutoGen fallback",
    description=(
        "1) Check in-memory TTL cache.\n"
        "2) On miss, call /search/api_context over HTTP.\n"
        "3) If a usable endpoint is found, return plan and cache it.\n"
        "4) Otherwise, try AutoGen (if USE_AUTOGEN=1)."
    ),
)
async def api_agent(req: ApiAgentRequest) -> ApiAgentResponse:
    request_id = str(uuid.uuid4())
    q = (req.q or "").strip()
    profile = req.profile or DEFAULT_PROFILE
    top_k = req.top_k or DEFAULT_TOP_K

    log.info(json.dumps({"event": "start", "request_id": request_id, "q": q, "profile": profile, "top_k": top_k}))

    # 1) Cache
    cached = _CACHE.get(q)
    if cached:
        log.info(json.dumps({"event": "cache_hit", "request_id": request_id, "endpoint": cached.get("endpoint")}))
        return ApiAgentResponse(request_id=request_id, status="ok", source="cache", plan=Plan(**cached))

    # 2) Retriever
    try:
        results = await _call_api_context(q=q, profile=profile, top_k=top_k)
        hits_count = len(results.get("results") or [])
        log.info(json.dumps({"event": "retriever_ok", "request_id": request_id, "hits": hits_count}))
    except Exception as e:
        err = str(e)
        log.error(json.dumps({"event": "retriever_error", "request_id": request_id, "error": err}))
        return ApiAgentResponse(request_id=request_id, status="error", error=f"retriever failed: {err}")

    # 3) Extract a plan candidate from retriever hits
    plan = _extract_plan(results)
    if plan:
        _CACHE.set(q, plan)
        log.info(json.dumps({"event": "plan_from_retriever", "request_id": request_id, "endpoint": plan.get("endpoint")}))
        return ApiAgentResponse(request_id=request_id, status="ok", source="retriever", plan=Plan(**plan))

    # 4) AutoGen fallback
    log.info(json.dumps({"event": "autogen_handoff", "request_id": request_id, "enabled": USE_AUTOGEN}))
    if USE_AUTOGEN:
        try:
            handoff = await plan_with_autogen(q, profile=profile)
            # ensure handoff contains expected fields for ApiAgentResponse
            log.info(json.dumps({"event": "autogen_result", "request_id": request_id, "result": handoff}))
            # plan_with_autogen returns dict like {"status":..., "plan": {...}, ...}
            return ApiAgentResponse(request_id=request_id, **handoff)
        except Exception as e:
            log.exception("autogen.exception %s", e)
            raise HTTPException(status_code=500, detail=f"AutoGen failed: {e}")

    # 5) Nothing found and AutoGen disabled
    reason = "No plan found and AutoGen disabled (set USE_AUTOGEN=1 to enable)."
    log.info(json.dumps({"event": "no_plan", "request_id": request_id, "reason": reason}))
    return ApiAgentResponse(request_id=request_id, status="needs_input", reason=reason)
