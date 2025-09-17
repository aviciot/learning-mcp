from __future__ import annotations
from typing import List, Dict, Any
import os, httpx

class EmbedProvider:
    OLLAMA = "ollama"
    CLOUDFLARE = "cloudflare"

class EmbeddingConfig:
    def __init__(self, profile: Dict[str, Any]):
        emb = (profile.get("embedding") or {})
        self.provider = os.getenv("EMBED_PROVIDER", emb.get("provider", "ollama")).lower()
        self.model = os.getenv("EMBED_MODEL", emb.get("model", "nomic-embed-text"))
        self.dim = int(emb.get("dim", 768))
        self.batch_size = int(emb.get("batch_size", 64))
        # provider-specific
        self.ollama_host = os.getenv("OLLAMA_HOST", (emb.get("ollama", {}) or {}).get("host", "http://localhost:11434"))
        self.cf_account_id = os.getenv("CF_ACCOUNT_ID", (emb.get("cloudflare", {}) or {}).get("account_id", ""))
        self.cf_api_token = os.getenv("CF_API_TOKEN", "")
        self.cf_model = os.getenv("CF_MODEL", (emb.get("cloudflare", {}) or {}).get("model", "@cf/baai/bge-small-en-v1.5"))

class Embedder:
    def __init__(self, cfg: EmbeddingConfig):
        self.cfg = cfg
        self.client = httpx.AsyncClient(timeout=30)

    async def close(self):
        await self.client.aclose()

    async def embed(self, texts: List[str]) -> List[List[float]]:
        out: List[List[float]] = []
        bs = self.cfg.batch_size
        for i in range(0, len(texts), bs):
            out.extend(await self._embed_batch(texts[i:i+bs]))
        return out

    async def _embed_batch(self, texts: List[str]) -> List[List[float]]:
        if self.cfg.provider == EmbedProvider.OLLAMA:
            return await self._ollama(texts)
        elif self.cfg.provider == EmbedProvider.CLOUDFLARE:
            return await self._cloudflare(texts)
        raise ValueError(f"Unsupported provider: {self.cfg.provider}")

    async def _ollama(self, texts: List[str]) -> List[List[float]]:
        url = f"{self.cfg.ollama_host.rstrip('/')}/api/embeddings"
        vecs = []
        for t in texts:
            r = await self.client.post(url, json={"model": self.cfg.model, "prompt": t})
            r.raise_for_status()
            data = r.json()
            vecs.append(data["embedding"])
        return vecs

    async def _cloudflare(self, texts: List[str]) -> List[List[float]]:
        if not self.cfg.cf_account_id or not self.cfg.cf_api_token:
            raise RuntimeError("Cloudflare credentials missing.")
        url = f"https://api.cloudflare.com/client/v4/accounts/{self.cfg.cf_account_id}/ai/run/{self.cfg.cf_model.lstrip('/')}"
        headers = {"Authorization": f"Bearer {self.cfg.cf_api_token}"}
        vecs = []
        for t in texts:
            r = await self.client.post(url, headers=headers, json={"text": t})
            r.raise_for_status()
            data = r.json()
            res = data.get("result", {})
            vec = res.get("data") if isinstance(res, dict) else res
            if not isinstance(vec, list):
                raise RuntimeError(f"Unexpected Cloudflare response: {data}")
            vecs.append(vec)
        return vecs
