# /app/src/learning_mcp/routes/search.py
"""
Semantic search over Qdrant (profile-driven) with improved logging.

Purpose:
- Embed the query via Ollama primary (CF fallback), search Qdrant, return top-K with scores/snippets.
- Log model/backend/dim used and quick diagnostics.

User question (example):
Q: "Why does my search return low scores?"
A: Check logs: you'll see model/backend/dim, collection used, and vector dim of the embedded query.
"""

from __future__ import annotations
from typing import Dict, Any, List, Optional
import logging

from fastapi import APIRouter, Body, HTTPException
from pydantic import BaseModel, Field

from learning_mcp.config import settings
from learning_mcp.embeddings import EmbeddingConfig, Embedder, EmbeddingError
from learning_mcp.vdb import VDB

router = APIRouter()
log = logging.getLogger("learning_mcp.search")

# ---------- Schemas ----------

class SearchRequest(BaseModel):
    profile: str = Field(..., description="Profile name in config/learning.yaml")
    q: str = Field(..., description="Natural language query")
    top_k: int = Field(5, gt=0, description="Number of nearest chunks to return")

    class Config:
        json_schema_extra = {
            "examples": [
             {
                "profile": "dahua-camera",
                "q": "reset camera to factory defaults",
                "top_k": 5
                }

            ]
        }

class SearchHit(BaseModel):
    score: float = Field(..., example=0.8453)
    text: Optional[str] = Field(None, description="Matched chunk snippet")
    doc_path: Optional[str] = Field(None, description="Original PDF path")
    chunk_idx: Optional[int] = Field(None, description="Chunk index within the doc")

class SearchResponse(BaseModel):
    status: str = Field(..., example="ok")
    results: List[SearchHit] = Field(default_factory=list)

# ---------- Endpoint ----------

@router.post(
    "/search",
    tags=["search"],
    summary="Semantic search over ingested PDFs",
    description=(
        "Loads the profile from **config/learning.yaml**, embeds the query using the configured "
        "provider/model (Ollama primary, CF fallback), searches Qdrant, and returns top-K snippets. "
        "Run `/ingest/jobs` first so there is data to search."
    ),
    response_model=SearchResponse,
)
async def search(body: SearchRequest = Body(...)) -> SearchResponse:
    profile_name = body.profile.strip()
    q = body.q.strip()
    top_k = body.top_k

    if not q:
        raise HTTPException(status_code=400, detail="Query 'q' must not be empty")

    profiles = settings.load_profiles()
    prof = next((p for p in profiles.get("profiles", []) if p.get("name") == profile_name), None)
    if not prof:
        raise HTTPException(
            status_code=404,
            detail=f"Profile '{profile_name}' not found in {settings.PROFILES_PATH}"
        )

    # Vector DB config
    vcfg: Dict[str, Any] = prof.get("vectordb", {}) or {}
    url: Optional[str] = vcfg.get("url")
    col: str = (vcfg.get("collections") or {}).get("docs", "docs_default")
    distance: str = (vcfg.get("distance") or "cosine")

    # Embedding config + VDB
    ecfg = EmbeddingConfig.from_profile(prof)
    vdb = VDB(url=url, collection=col, dim=ecfg.dim, distance=distance)

    log.info(
        "search.plan profile=%s collection=%s distance=%s model=%s cf_model=%s dim=%s top_k=%s",
        profile_name, col, distance, ecfg.ollama_model, (ecfg.cf_model or "-"), ecfg.dim, top_k
    )

    # Ensure collection exists and has data
    try:
        exists = vdb.collection_exists()  # method added in vdb.py
        cnt = vdb.count() if exists else 0
    except Exception as e:
        log.error("search.vdb.error profile=%s err=%s", profile_name, e)
        return SearchResponse(status="error", results=[])

    if not exists or cnt == 0:
        log.warning("search.empty profile=%s collection=%s exists=%s count=%s", profile_name, col, exists, cnt)
        return SearchResponse(status="error", results=[])

    emb = Embedder(ecfg)
    try:
        vec = (await emb.embed([q]))[0]
        log.info("search.embed.done q_len=%s vec_dim=%s", len(q), len(vec))

        hits = vdb.search(vec, top_k=top_k) or []
        results = [
            SearchHit(
                score=h.score,
                text=(h.payload or {}).get("text"),
                doc_path=(h.payload or {}).get("doc_path"),
                chunk_idx=(h.payload or {}).get("chunk_idx"),
            )
            for h in hits
        ]
        return SearchResponse(status="ok", results=results)
    except EmbeddingError as e:
        log.error("search.embed.fail profile=%s err=%s", profile_name, e)
        raise HTTPException(status_code=500, detail=f"Embedding failed: {e}") from e
    finally:
        await emb.close()


