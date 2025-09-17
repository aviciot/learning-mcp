from typing import Dict, Any, List
from qdrant_client import QdrantClient
from qdrant_client.http.models import Distance, VectorParams, PointStruct

class VDB:
    def __init__(self, url: str, collection: str, dim: int):
        self.url = url
        self.collection = collection
        self.client = QdrantClient(url=url)
        self.dim = dim

    def ensure_collection(self):
        if self.collection not in [c.name for c in self.client.get_collections().collections]:
            self.client.recreate_collection(
                collection_name=self.collection,
                vectors_config=VectorParams(size=self.dim, distance=Distance.COSINE),
            )

    def upsert(self, vectors: List[List[float]], payloads: List[Dict[str, Any]]):
        points = [PointStruct(id=i, vector=vectors[i], payload=payloads[i]) for i in range(len(vectors))]
        self.client.upsert(collection_name=self.collection, points=points)

    def search(self, query_vec: List[float], top_k: int = 5):
        return self.client.search(collection_name=self.collection, query_vector=query_vec, limit=top_k)
