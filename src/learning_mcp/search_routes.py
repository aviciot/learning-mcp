"""Search API routes for AutoGen integration."""
import logging
import re
from typing import Dict, Any, List, Optional

from fastapi import APIRouter, Body
from pydantic import BaseModel, Field

from learning_mcp.embeddings import EmbeddingConfig, Embedder
from learning_mcp.vdb import VDB
from learning_mcp.config import settings

log = logging.getLogger("learning_mcp.search")
router = APIRouter()

# ---- Heuristics for hints (optional but useful for api_plan) ----
_PATH_RE = re.compile(r"(/(?:api|public)[^\s\"'()<>]+)")
_KV_RE = re.compile(r"([A-Za-z][A-Za-z0-9_]*?)\s*=\s*([^\s,;&)]+)")


class SearchRequest(BaseModel):
    q: str = Field(..., description="Query text")
    profile: str = Field(..., description="Profile name; also used as doc_id filter")
    top_k: int = Field(8, ge=1, le=100)
    read_only: bool = Field(True, description="No side effects; for logging/hints")


class SearchResponse(BaseModel):
    ok: bool
    results: List[Dict[str, Any]]


def _load_profile(profile_name: str) -> Dict[str, Any]:
    profiles = settings.load_profiles()
    return next((p for p in profiles.get("profiles", []) if p.get("name") == profile_name), {}) or {}


def _build_embedder(profile_name: str) -> Embedder:
    prof = _load_profile(profile_name)
    ecfg = EmbeddingConfig.from_profile(prof)
    return Embedder(ecfg)


def _build_vdb(profile_name: str) -> VDB:
    prof = _load_profile(profile_name)
    vcfg = prof.get("vectordb", {}) or {}
    dim = EmbeddingConfig.from_profile(prof).dim
    return VDB(
        url=vcfg.get("url"),
        collection=vcfg.get("collection"),
        dim=dim,
        distance=(vcfg.get("distance") or "cosine")
    )


def _extract_url_candidates(text: str) -> List[str]:
    if not text:
        return []
    urls = []
    for m in _PATH_RE.finditer(text):
        path = m.group(1).rstrip(".,);]")
        if path and path not in urls:
            urls.append(path)
    return urls[:3]


def _extract_query_candidates(text: str) -> Dict[str, Any]:
    if not text:
        return {}
    out: Dict[str, Any] = {}
    for k, v in _KV_RE.findall(text):
        if k not in out:
            out[k] = v
        if len(out) >= 8:
            break
    return out


def _method_hint_from_text(text: str) -> Optional[str]:
    if not text:
        return None
    low = text.lower()
    if "post " in low or " post/" in low or "create " in low or "add " in low:
        return "POST"
    if "put " in low or "update " in low or "replace " in low:
        return "PUT"
    if "patch " in low or "modify " in low:
        return "PATCH"
    if "delete " in low or " remove " in low:
        return "DELETE"
    return "GET"


@router.post("/search/api_context", response_model=SearchResponse, tags=["search"])
async def api_context(body: SearchRequest = Body(...)) -> SearchResponse:
    """
    Dense semantic search over the profile's collection.
    Returns minimal fields + optional 'hints' used by AutoGen planners.
    """
    emb = _build_embedder(body.profile)
    vdb = _build_vdb(body.profile)
    
    try:
        qvec = (await emb.embed([body.q]))[0]

        # Primary: filter by canonical doc_id
        hits = vdb.search(qvec, top_k=body.top_k, filter_by={"doc_id": body.profile})
        if not hits:
            # Legacy fallback for older ingests that only stored 'profile'
            hits = vdb.search(qvec, top_k=body.top_k, filter_by={"profile": body.profile})
            if hits:
                log.warning("search.legacy_fallback profile=%s used=profile missing=doc_id", body.profile)

        results: List[Dict[str, Any]] = []
        for pt in hits:
            payload = getattr(pt, "payload", {}) or {}
            txt = payload.get("text") or ""
            snippet = txt[:360] + ("…" if len(txt) > 360 else "")

            # Optional best-effort hints for planners
            url_candidates = _extract_url_candidates(snippet)
            method_hint = _method_hint_from_text(snippet)
            query_candidates = _extract_query_candidates(snippet)

            results.append({
                "id": getattr(pt, "id", None),
                "score": float(getattr(pt, "score", 0.0) or 0.0),
                "doc_id": payload.get("doc_id") or payload.get("profile"),
                "chunk_id": payload.get("chunk_id") or payload.get("hash") or getattr(pt, "id", None),
                "doc_path": payload.get("doc_path"),
                "chunk_idx": payload.get("chunk_idx"),
                "snippet": snippet,
                "hints": {
                    "url_candidates": url_candidates or None,
                    "method_hint": method_hint,
                    "query_candidates": (query_candidates or None),
                },
            })

        return SearchResponse(ok=True, results=results)
    finally:
        await emb.close()
