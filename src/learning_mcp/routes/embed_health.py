import os
import httpx
from fastapi import APIRouter

router = APIRouter()


@router.get("/embed/health")
async def embed_health():
    """Check whether the embedding provider is reachable.

    Call `GET /embed/health` to probe the embedding service defined by
    environment variables (currently supports Ollama). The response confirms
    connectivity, lists available models, and points out configuration issues
    so you can fix them before embedding large batches.
    """
    provider = os.getenv("EMBED_PROVIDER", "ollama")
    model = os.getenv("EMBED_MODEL", None)

    if provider.lower() != "ollama":
        return {
            "status": "skip",
            "reason": "health check currently implemented for provider=ollama",
            "provider": provider,
            "model": model,
        }

    host = os.getenv("OLLAMA_HOST", "http://localhost:11434").rstrip("/")
    url = f"{host}/api/tags"
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            r = await client.get(url)
            r.raise_for_status()
            data = r.json()
        return {
            "status": "ok",
            "provider": "ollama",
            "host": host,
            "reachable": True,
            "models_found": [m.get("name") for m in (data or {}).get("models", [])],
            "model_env": model,
        }
    except Exception as e:
        return {
            "status": "error",
            "provider": "ollama",
            "host": host,
            "reachable": False,
            "error": str(e),
            "hint": "Ensure Ollama port is published and OLLAMA_HOST points to host.docker.internal:11434",
        }
