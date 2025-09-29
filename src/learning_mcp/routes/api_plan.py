# src/learning_mcp/routes/api_plan.py
from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field
from fastapi import APIRouter, HTTPException, Request
import logging
import re

from utils.inprocess_client import call_inprocess  # in-process HTTP helper

logger = logging.getLogger("learning_mcp.api_plan")
router = APIRouter()

# ---- Helpers ----
PATH_RE = re.compile(r"(/(?:api|public)[^\s\"'()<>]+)")

class ApiPlanRequest(BaseModel):
    profile: str = Field(..., description="Profile from learning.yaml")
    q: str = Field(..., description="User question to search in docs")
    top_k: int = Field(5, ge=1, le=10, description="How many hints to fetch")
    threshold: float = Field(0.65, ge=0.0, le=1.0, description="Min score to accept")

class ApiPlanResponse(BaseModel):
    status: str
    request: Optional[Dict[str, Any]] = None
    evidence: Optional[Dict[str, Any]] = None
    alternatives: Optional[List[Dict[str, Any]]] = None
    confidence: Optional[float] = None
    notes: Optional[List[str]] = None
    reason: Optional[str] = None

def _prefer_path(snippet: str) -> Optional[str]:
    """Extract the first likely endpoint path from a snippet, e.g. /public/core/v3/users"""
    if not snippet:
        return None
    m = PATH_RE.search(snippet)
    return m.group(1).rstrip(".,);]") if m else None

@router.post(
    "/api_plan",
    tags=["api"],
    summary="Plan a safe (GET) API request from api_context hints",
    operation_id="api_plan",
    description="Deterministic planner: calls api_context, picks a GET endpoint, builds a dry-run request. No outbound vendor API calls."
)
async def api_plan(req: ApiPlanRequest, request: Request) -> ApiPlanResponse:
    """
    Build a read-only API request suggestion by consulting the local `api_context` route.

    We call the `api_context` route IN-PROCESS via httpx's ASGI adapter using the route NAME
    (must be defined as name='api_context' on the search API router). This avoids any need
    for SERVICE_BASE_URL / PATH config and skips the network hop.
    """
    # 1) Call the local api_context route by name (in-process)
    logger.info(
        "api_plan: calling route[name=api_context] profile=%s q=%r top_k=%s",
        req.profile, req.q, req.top_k
    )

    try:
        r = await call_inprocess(
            app=request.app,
            route_name="api_context",
            method="POST",
            json={"profile": req.profile, "q": req.q, "top_k": req.top_k},
        )
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"api_context call failed: {e}")

    if r.status_code != 200:
        body_preview = r.text[:300] if hasattr(r, "text") else "<no body>"
        logger.error("api_plan: api_context HTTP %s: %s", r.status_code, body_preview)
        raise HTTPException(status_code=502, detail=f"api_context HTTP {r.status_code}")

    try:
        ctx = r.json()
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"api_context JSON parse error: {e}")

    hits = (ctx or {}).get("results") or []
    logger.info("api_plan: api_context hits=%d", len(hits))
    if not hits:
        return ApiPlanResponse(status="no-plan", reason="No results from api_context")

    # 2) Collect candidates above threshold
    candidates: List[Dict[str, Any]] = []
    for h in hits:
        score = float(h.get("score") or 0.0)
        if score < req.threshold:
            continue
        hints = h.get("hints") or {}
        method = (hints.get("method_hint") or "GET").upper()
        path_list = hints.get("url_candidates") or []
        if not path_list:
            inferred = _prefer_path(h.get("snippet") or "")
            if inferred:
                path_list = [inferred]
        if path_list:
            candidates.append({
                "score": score,
                "method": method,
                "path": path_list[0],
                "query_candidates": hints.get("query_candidates") or {},
                "snippet": h.get("snippet") or ""
            })

    # 2b) Soft retry with lower threshold if nothing passed
    if not candidates and req.threshold > 0.0:
        for h in hits:
            hints = h.get("hints") or {}
            path_list = hints.get("url_candidates") or []
            if not path_list:
                inferred = _prefer_path(h.get("snippet") or "")
                if inferred:
                    path_list = [inferred]
            if path_list:
                candidates.append({
                    "score": float(h.get("score") or 0.0),
                    "method": (hints.get("method_hint") or "GET").upper(),
                    "path": path_list[0],
                    "query_candidates": hints.get("query_candidates") or {},
                    "snippet": h.get("snippet") or ""
                })

    if not candidates:
        top = max(hits, key=lambda x: x.get("score", 0))
        return ApiPlanResponse(
            status="no-plan",
            reason="No clean endpoint found in results",
            evidence={"score": top.get("score"), "snippet": (top.get("snippet") or "")[:500]}
        )

    # 3) De-duplicate by path (keep the highest-score candidate per unique path)
    dedup: Dict[str, Dict[str, Any]] = {}
    for c in candidates:
        p = c["path"]
        if p not in dedup or c["score"] > dedup[p]["score"]:
            dedup[p] = c
    candidates = list(dedup.values())

    # 4) Rank: prefer /public/ and /v3/; then by score
    def rank_key(c: Dict[str, Any]):
        bonus_public = 1 if "/public/" in c["path"] else 0
        bonus_v3 = 1 if "/v3/" in c["path"] else 0
        return (bonus_public, bonus_v3, c["score"])

    candidates.sort(key=rank_key, reverse=True)
    best = candidates[0]

    # 5) Safety: force GET + read_only
    notes: List[str] = []
    if best["method"] != "GET":
        notes.append(f"Method hint '{best['method']}' overridden to GET (read-only).")

    query: Dict[str, Any] = {}
    for k, v in (best.get("query_candidates") or {}).items():
        query[k] = v  # keep placeholders/defaults

    request_obj = {
        "profile": req.profile,
        "method": "GET",
        "path": best["path"],
        "query": query,
        "headers": {"Accept": "application/json"},
        "read_only": True
    }

    alternatives = [
        {"path": c["path"], "score": c["score"], "method": c["method"]}
        for c in candidates[1:3]
    ]

    return ApiPlanResponse(
        status="ok",
        request=request_obj,
        evidence={
            "score": best["score"],
            "snippet": best["snippet"],
            "method_hint": best["method"],
            "path": best["path"],
            "query_candidates": best.get("query_candidates") or {},
        },
        alternatives=alternatives or None,
        confidence=best["score"],
        notes=notes or None
    )
