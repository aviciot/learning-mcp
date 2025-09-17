from typing import Any, Dict
from fastapi import APIRouter

from ..config import settings
from ..vdb import VDB

router = APIRouter()


@router.get("/config", tags=["config"])
def get_config():
    """Return a basic view of the parsed configuration.

    Call `GET /config` to confirm the service can read `config/learning.yaml`
    and `.env`. The response lists the profile names plus the runtime
    environment data, which is handy for troubleshooting container setups.
    """
    profiles = settings.load_profiles()
    names = [p.get("name") for p in profiles.get("profiles", [])]
    return {
        "status": "ok",
        "profiles": names,
        "profiles_raw_present": bool(profiles),
        "env": settings.ENV,
        "port": settings.PORT,
    }


@router.get(
    "/profiles",
    tags=["config"],
    summary="List profiles with vector DB status",
    description="Returns configured profiles along with the target Qdrant collection and indexed point counts.",
)
def list_profiles():
    """Summarise every profile and its Qdrant collection.

    Hit `GET /profiles` to see which documents belong to each profile, the
    Qdrant collection they target, and how many vectors are currently indexed.
    It also reports connection problems, making it a quick health check after
    running `/ingest`.
    """
    payload = settings.load_profiles()
    profiles = payload.get("profiles", [])
    summaries: list[Dict[str, Any]] = []

    for prof in profiles:
        name = prof.get("name") or "<unnamed>"
        vectordb = (prof.get("vectordb") or {})
        documents = prof.get("documents") or []
        collections = (vectordb.get("collections") or {})
        docs_collection = collections.get("docs")
        vdb_url = vectordb.get("url")
        dim_raw = (prof.get("embedding") or {}).get("dim", 768)
        try:
            dim = int(dim_raw)
        except (TypeError, ValueError):
            dim = 768

        summary: Dict[str, Any] = {
            "name": name,
            "documents": documents,
            "collection": docs_collection,
            "vectordb_url": vdb_url,
            "points_indexed": 0,
            "status": "unavailable",
        }

        if not vdb_url or not docs_collection:
            summary["status"] = "incomplete-config"
            summaries.append(summary)
            continue

        try:
            vdb = VDB(url=vdb_url, collection=docs_collection, dim=dim)
            if not vdb.collection_exists():
                summary["status"] = "collection-missing"
            else:
                count = vdb.count_points()
                summary["points_indexed"] = count
                summary["status"] = "ready" if count else "empty"
        except Exception as exc:  # best-effort diagnostic for UI calls
            summary["status"] = "error"
            summary["error"] = str(exc)

        summaries.append(summary)

    return {"status": "ok", "profiles": summaries}
