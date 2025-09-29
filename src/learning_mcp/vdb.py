# /src/learning_mcp/vdb.py
"""
Qdrant wrapper (clean, robust).

Purpose:
- Manage a single Qdrant collection (ensure/create, validate shape).
- Safe upsert with idempotent IDs (use supplied IDs or payload['hash']).
- Batch upserts, strict vector validation, simple search & utilities.

Example (PowerShell):
  docker compose exec api python /app/src/tools/run_snippet.py `
    --module learning_mcp.vdb `
    --call quick_health `
    --kwargs '{}'
"""

from __future__ import annotations
from typing import List, Dict, Any, Optional, Iterable, Tuple
from uuid import uuid4
import os
import math

from qdrant_client import QdrantClient
from qdrant_client.http.models import Distance, VectorParams, PointStruct, Filter, FieldCondition, MatchValue

from learning_mcp.config import settings

# ---------- Distance mapping ----------

_DISTANCE_MAP = {
    "cosine": Distance.COSINE,
    "euclid": Distance.EUCLID,
    "l2": Distance.EUCLID,
    "dot": Distance.DOT,
    "dotproduct": Distance.DOT,
}

UPSERT_BATCH = int(os.getenv("VDB_UPSERT_BATCH", "256"))  # safe default for Qdrant HTTP
ALLOW_RECREATE = os.getenv("VDB_ALLOW_RECREATE", "1") not in ("0", "false", "False")


def _sanitize_vec(vec: List[float]) -> None:
    if not isinstance(vec, list) or not vec:
        raise ValueError("Vector must be a non-empty list")
    # Cheap checks for NaN/Inf/bool/None
    for v in vec:
        if v is None or isinstance(v, bool) or math.isnan(float(v)) or math.isinf(float(v)):
            raise ValueError("Invalid number in embedding vector (NaN/Inf/None/bool)")


class VDB:
    """Thin, predictable wrapper around a single Qdrant collection."""

    def __init__(
        self,
        url: Optional[str] = None,
        collection: Optional[str] = None,
        dim: Optional[int] = None,
        distance: str = "cosine",
        prefer_recreate_on_mismatch: bool = True,
    ):
        self.url = url or settings.VECTOR_DB_URL
        self.collection = collection or settings.VECTOR_COLLECTION
        self.dim = int(dim or settings.vector_dim)

        # normalize distance safely
        self.distance = _DISTANCE_MAP.get(str(distance).lower(), Distance.COSINE)
        self.prefer_recreate_on_mismatch = prefer_recreate_on_mismatch

        self.client = QdrantClient(url=self.url)

    # ---------- Collection management ----------

    def ensure_collection(self) -> None:
        """Create the collection if missing; NEVER recreate on exists (avoid accidental wipes)."""
        try:
            self.client.get_collection(self.collection)
            return  # exists: do nothing
        except Exception:
            # create fresh if missing
            self.client.recreate_collection(
                collection_name=self.collection,
                vectors_config=VectorParams(size=self.dim, distance=self.distance),
            )

    def truncate(self) -> None:
        """Drop and recreate the collection with current dim/distance."""
        try:
            self.client.delete_collection(self.collection)
        except Exception:
            pass
        self.client.recreate_collection(
            collection_name=self.collection,
            vectors_config=VectorParams(size=self.dim, distance=self.distance),
        )

    # ---------- Data operations ----------

    def upsert(
        self,
        vectors: List[List[float]],
        payloads: List[Dict[str, Any]],
        ids: Optional[List[str]] = None,
    ) -> List[str]:
        """
        Upsert vectors with payloads. Returns point IDs.
        - If `ids` not provided, and payload contains 'hash', that hash is used as the ID (idempotent).
        - Otherwise, UUID v4 is used.
        """
        if len(vectors) != len(payloads):
            raise ValueError("vectors and payloads length mismatch")
        if ids is not None and len(ids) != len(vectors):
            raise ValueError("ids length must match vectors length when provided")
        if not vectors:
            return []

        # simple dimension & hygiene guard
        d0 = len(vectors[0])
        if d0 != self.dim:
            raise ValueError(f"Vector dim mismatch: got {d0}, expected {self.dim}. Check VECTOR_DIM & model.")
        for v in vectors:
            if len(v) != self.dim:
                raise ValueError(f"Inconsistent vector dims: found {len(v)}, expected {self.dim}.")
            _sanitize_vec(v)

        self.ensure_collection()

        # Prepare IDs
        if ids is None:
            ids = []
            for i in range(len(vectors)):
                pid = None
                h = payloads[i].get("hash")
                if isinstance(h, str) and h:
                    pid = h  # deterministic id if hash provided
                ids.append(pid or str(uuid4()))
        else:
            ids = list(ids)

        # Batch upserts for large payloads
        written: List[str] = []
        for start in range(0, len(vectors), UPSERT_BATCH):
            end = min(start + UPSERT_BATCH, len(vectors))
            batch_points = [
                PointStruct(id=ids[i], vector=vectors[i], payload=payloads[i])
                for i in range(start, end)
            ]
            self.client.upsert(collection_name=self.collection, points=batch_points)
            written.extend(ids[start:end])

        return written

    def search(
        self,
        query_vec: List[float],
        top_k: int = 5,
        *,
        filter_by: Optional[Dict[str, Any]] = None,
        with_payload: bool = True,
    ):
        """
        KNN search by vector. Optional `filter_by` is a simple equality dict merged into a Qdrant Filter.
        Example: filter_by={"doc_id": "user_guide_v1"}
        """
        if len(query_vec) != self.dim:
            raise ValueError(f"Query vector dim mismatch: got {len(query_vec)}, expected {self.dim}.")
        _sanitize_vec(query_vec)
        self.ensure_collection()

        qfilter: Optional[Filter] = None
        if filter_by:
            must = []
            for k, v in filter_by.items():
                must.append(FieldCondition(key=k, match=MatchValue(value=v)))
            qfilter = Filter(must=must)

        return self.client.search(
            collection_name=self.collection,
            query_vector=query_vec,
            limit=top_k,
            with_payload=with_payload,
            query_filter=qfilter,
        )

    def search_raw(self, **kwargs):
        """Direct passthrough to qdrant_client.search for advanced callers."""
        self.ensure_collection()
        return self.client.search(collection_name=self.collection, **kwargs)

    def get_by_ids(self, ids: List[str]) -> List[Any]:
        """Retrieve points by IDs."""
        if not ids:
            return []
        self.ensure_collection()
        return self.client.retrieve(collection_name=self.collection, ids=ids, with_payload=True, with_vectors=False)

    def delete_by_ids(self, ids: List[str]) -> None:
        """Delete points by IDs."""
        if not ids:
            return
        self.ensure_collection()
        self.client.delete(collection_name=self.collection, points_selector=ids)

    def count(self) -> int:
        """Exact number of stored points."""
        self.ensure_collection()
        res = self.client.count(collection_name=self.collection, exact=True)
        return int(getattr(res, "count", 0))

    # ---------- Utilities ----------

    def quick_health(self) -> Dict[str, Any]:
        """Lightweight health info for diagnostics."""
        try:
            self.ensure_collection()
            return {
                "url": self.url,
                "collection": self.collection,
                "dim": self.dim,
                "distance": str(self.distance.value if hasattr(self.distance, "value") else self.distance),
                "count": self.count(),
                "ok": True,
            }
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def collection_exists(self) -> bool:
        """Check if collection exists in Qdrant."""
        try:
            self.client.get_collection(self.collection)
            return True
        except Exception:
            return False
