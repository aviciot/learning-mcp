# src/learning_mcp/routes/search.py
"""
FastAPI route for semantic search against ingested documents in Qdrant.

- Loads profile and vector DB config from config/learning.yaml
- Embeds the user query with the configured provider/model
- Searches Qdrant for top-K similar chunks
- Returns snippet, score, and doc path
- Validates collection exists before querying

Example request (Swagger/PowerShell):
Invoke-RestMethod -Uri http://localhost:8013/search -Method Post -ContentType 'application/json' -Body '{"profile":"informatica-cloud","q":"repository details","top_k":5}'
"""

from fastapi import APIRouter, Body
from ..config import settings
from ..embeddings import EmbeddingConfig, Embedder
from ..vdb import VDB

router = APIRouter()


@router.post("/search", tags=["search"])
async def search(payload: dict = Body(..., example={"profile": "informatica-cloud", "q": "start task", "top_k": 5})):
    """Search the indexed chunks for a profile.

    Use `POST /search` with a JSON body like `{ "profile": "name", "q": "your question", "top_k": 5 }`.
    The endpoint embeds the query using the profile's provider, runs a similarity
    search in Qdrant, and returns the best-matching snippets with their scores
    and original file paths. Make sure `/ingest` has been run first so the
    collection contains vectors to search.
    """
    profile_name = payload.get("profile", "informatica-cloud")
    q = payload.get("q", "")
    top_k = int(payload.get("top_k", 5))

    if not q.strip():
        return {"status": "error", "error": "query 'q' must not be empty"}

    profiles = settings.load_profiles()
    prof = next((p for p in profiles.get("profiles", []) if p.get("name") == profile_name), None)
    if not prof:
        return {"status": "error", "error": f"profile '{profile_name}' not found"}

    vcfg = prof.get("vectordb", {})
    url = vcfg.get("url")
    col = (vcfg.get("collections") or {}).get("docs", "docs_default")

    ecfg = EmbeddingConfig(prof)
    vdb = VDB(url=url, collection=col, dim=ecfg.dim)

    # Verify collection has data
    collections = [c.name for c in vdb.client.get_collections().collections]
    if col not in collections:
        return {"status": "error", "error": f"collection '{col}' not found or empty, did you run /ingest first?"}

    emb = Embedder(ecfg)
    try:
        vec = (await emb.embed([q]))[0]
        hits = vdb.search(vec, top_k=top_k)
        if not hits:
            return {"status": "ok", "results": [], "note": "no matches found"}

        results = []
        for h in hits:
            payload = h.payload or {}
            results.append({
                "score": h.score,
                "text": payload.get("text"),
                "doc_path": payload.get("doc_path"),
                "chunk_idx": payload.get("chunk_idx"),
            })
        return {"status": "ok", "results": results}
    finally:
        await emb.close()
