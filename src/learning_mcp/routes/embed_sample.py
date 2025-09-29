# src/learning_mcp/routes/embed_sample.py

from fastapi import APIRouter, Query, HTTPException

from learning_mcp.config import settings
from learning_mcp.embeddings import EmbeddingConfig, Embedder, EmbeddingError

router = APIRouter()

@router.get(
    "/debug/embed",
    tags=["debug"],
    summary="Embedding sanity check",
    description="Returns vector length and backend/model for a sample text.",
)
async def embed_sample(
    text: str = Query("hello world", description="Text to embed"),
    profile: str = Query("informatica-cloud", description="Profile name from YAML"),
):
    profiles = settings.load_profiles()
    prof = next((p for p in profiles.get("profiles", []) if p.get("name") == profile), None)
    if not prof:
        raise HTTPException(status_code=404, detail=f"Profile '{profile}' not found in {settings.PROFILES_PATH}")

    cfg = EmbeddingConfig.from_profile(prof)
    emb = Embedder(cfg)

    try:
        vecs = await emb.embed([text])
        vec = vecs[0] if vecs else []
        return {
            "status": "ok",
            "profile": profile,
            "backend": "cloudflare" if cfg.cf_model else "ollama",
            "model": cfg.cf_model or cfg.ollama_model,
            "vector_len": len(vec),
            "dim_expected": cfg.dim,
        }
    except EmbeddingError as e:
        raise HTTPException(status_code=500, detail=f"Embedding failed: {e}") from e
    finally:
        await emb.close()
