# src/learning_mcp/routes/embed_sample.py
"""
Debug endpoint to verify embedding provider connectivity (Ollama/Cloudflare).

Purpose:
- Accepts a short text and returns the embedding vector length.
- Confirms provider/model from YAML/env are working before full ingest.

Example (PowerShell):
Invoke-RestMethod -Uri 'http://localhost:8013/debug/embed?text=hello&profile=informatica-cloud' -Method GET
"""

from fastapi import APIRouter, Query
from ..config import settings
from ..embeddings import EmbeddingConfig, Embedder

router = APIRouter()

@router.get("/debug/embed", tags=["debug"], summary="Embedding sanity check", description="Returns vector length for a sample text.")
async def embed_sample(
    text: str = Query("hello world", description="Text to embed"),
    profile: str = Query("informatica-cloud", description="Profile name from YAML"),
):
    profiles = settings.load_profiles()
    prof = next((p for p in profiles.get("profiles", []) if p.get("name") == profile), None)
    if not prof:
        return {"status": "error", "error": f"profile '{profile}' not found"}

    cfg = EmbeddingConfig(prof)
    emb = Embedder(cfg)
    try:
        vecs = await emb.embed([text])
        vec = vecs[0] if vecs else []
        return {
            "status": "ok",
            "provider": cfg.provider,
            "model": cfg.model,
            "vector_len": len(vec),
        }
    finally:
        await emb.close()
