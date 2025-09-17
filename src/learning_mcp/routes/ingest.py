# src/learning_mcp/routes/ingest.py
"""
FastAPI route for ingesting PDF documents into Qdrant.

- Loads profile from config/learning.yaml
- Verifies that each referenced PDF file exists inside /app/data
- Extracts text, chunks, embeds, and upserts into Qdrant

Example request (Swagger/PowerShell):
Invoke-RestMethod -Uri http://localhost:8013/ingest -Method Post -ContentType 'application/json' -Body '{"profile":"informatica-cloud"}'
"""

import os
from fastapi import APIRouter, Body
from ..config import settings
from ..embeddings import EmbeddingConfig, Embedder
from ..pdf_loader import extract_text
from ..chunker import chunk_text
from ..vdb import VDB

router = APIRouter()


@router.post("/ingest", tags=["ingest"])
async def ingest(payload: dict = Body(..., example={"profile": "informatica-cloud"})):
    """Ingest documents for a profile into Qdrant.

    Send `POST /ingest` with `{ "profile": "name" }` to load that profile's
    PDFs. The endpoint checks the files exist, slices them into overlapping
    chunks, generates embeddings, and stores the vectors in the configured
    Qdrant collection. Use this before hitting `/search` so queries have data
    to retrieve.
    """
    profile_name = payload.get("profile", "informatica-cloud")
    profiles = settings.load_profiles()
    prof = next((p for p in profiles.get("profiles", []) if p.get("name") == profile_name), None)
    if not prof:
        return {"status": "error", "error": f"profile '{profile_name}' not found"}

    docs = prof.get("documents", [])
    if not docs:
        return {"status": "error", "error": "no documents in profile"}

    # vector db settings
    vcfg = prof.get("vectordb", {})
    url = vcfg.get("url")
    col = (vcfg.get("collections") or {}).get("docs", "docs_default")

    ecfg = EmbeddingConfig(prof)
    vdb = VDB(url=url, collection=col, dim=ecfg.dim)
    vdb.ensure_collection()

    emb = Embedder(ecfg)
    total_chunks = 0
    missing_files = []

    try:
        for d in docs:
            if d.get("type") != "pdf":
                continue
            path = d.get("path")
            if not path or not os.path.exists(path):
                missing_files.append(path or "<missing path>")
                continue

            text = extract_text(path)
            chunks = chunk_text(
                text,
                size=int((prof.get("chunking") or {}).get("size", 1200)),
                overlap=int((prof.get("chunking") or {}).get("overlap", 200)),
            )
            vecs = await emb.embed(chunks)
            payloads = [
                {"profile": profile_name, "doc_path": path, "chunk_idx": i, "text": chunks[i]}
                for i in range(len(chunks))
            ]
            vdb.upsert(vecs, payloads)
            total_chunks += len(chunks)

        return {
            "status": "ok",
            "profile": profile_name,
            "chunks_indexed": total_chunks,
            "collection": col,
            "missing_files": missing_files,
        }
    finally:
        await emb.close()
