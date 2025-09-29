# /app/src/learning_mcp/embeddings.py
"""
Unified embeddings with primary/fallback selection + per-request logging.

Enhancements:
- EMBED_PACING_MS applies to BOTH Cloudflare and Ollama.
- Timing/outcome logs (duration ms, backend).
- Input trimming via EMBED_MAX_CHARS; vector sanitization (no NaN/Inf).
- Optional caching hook: pass `ids` aligned with `texts`, and a `cache`
  (dict-like or object with get/set). Cache short-circuits hits.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Dict, Any, Tuple, Iterable
import asyncio
import logging
import os
import time
import math
import random

import httpx
from httpx import HTTPStatusError

log = logging.getLogger("learning_mcp.embeddings")

EMBED_PACING_MS = int(os.getenv("EMBED_PACING_MS", "150"))
EMBED_MAX_CHARS = int(os.getenv("EMBED_MAX_CHARS", "8000"))  # trim long inputs defensively


# ---------------------------
# Configuration
# ---------------------------

@dataclass(frozen=True)
class EmbeddingConfig:
    # Expected dimension
    dim: int

    # Primary/fallback
    primary: str = "ollama"                 # "ollama" | "cloudflare"
    fallback: Optional[str] = None          # same choices, optional

    # Ollama
    ollama_host: str = ""                   # e.g. "http://host.docker.internal:11434"
    ollama_model: str = ""                  # e.g. "nomic-embed-text" or "nomic-embed-text-v1.5"
    keep_alive: str = os.getenv("EMBED_KEEP_ALIVE", "15m")
    batch_size: int = 32                    # kept for compatibility; concurrency drives throughput
    timeout_seconds: float = float(os.getenv("EMBED_TIMEOUT_SECONDS", "120"))
    max_retries: int = int(os.getenv("EMBED_MAX_RETRIES", "2"))

    # Cloudflare (optional)
    cf_account_id: Optional[str] = None
    cf_api_token: Optional[str] = None
    cf_model: Optional[str] = None          # e.g. "@cf/baai/bge-small-en-v1.5"

    @staticmethod
    def from_profile(profile: Dict[str, Any]) -> "EmbeddingConfig":
        """
        Expected profile shape:

        embedding:
          dim: 768
          backend:
            primary: ollama           # or 'cloudflare'
            fallback: cloudflare      # optional
          keep_alive: "15m"
          batch_size: 32
          timeout_seconds: 120
          ollama:
            host: "http://host.docker.internal:11434"
            model: "nomic-embed-text"
          cloudflare:
            account_id: "..."
            api_token: "..."
            model: "@cf/baai/bge-small-en-v1.5"
        """
        emb = profile.get("embedding", {}) or {}
        ol = emb.get("ollama", {}) or {}
        cf = emb.get("cloudflare", {}) or {}
        be = emb.get("backend", {}) or {}

        dim = int(emb.get("dim", 768))

        # Primary/fallback (lowercased, validated)
        primary = str(be.get("primary", os.getenv("EMBED_PRIMARY", "ollama"))).strip().lower()
        fallback = be.get("fallback", os.getenv("EMBED_FALLBACK", None))
        fallback = str(fallback).strip().lower() if fallback else None

        def _ok(name: Optional[str]) -> Optional[str]:
            return name if name in ("ollama", "cloudflare") else None

        primary = _ok(primary) or "ollama"
        fallback = _ok(fallback)

        # Ollama config (not strictly required if primary=cloudflare and no fallback=ollama)
        ollama_host = (ol.get("host") or os.getenv("OLLAMA_HOST", "")).rstrip("/")
        ollama_model = ol.get("model") or os.getenv("EMBED_MODEL", "nomic-embed-text")

        keep_alive = str(emb.get("keep_alive", os.getenv("EMBED_KEEP_ALIVE", "15m")))
        batch_size = int(emb.get("batch_size", 32))
        timeout_seconds = float(emb.get("timeout_seconds", os.getenv("EMBED_TIMEOUT_SECONDS", 120)))
        max_retries = int(os.getenv("EMBED_MAX_RETRIES", "2"))

        # Cloudflare
        cf_account_id = cf.get("account_id") or os.getenv("CF_ACCOUNT_ID")
        cf_api_token  = cf.get("api_token")  or os.getenv("CF_API_TOKEN")
        cf_model      = cf.get("model")      or os.getenv("CF_EMBED_MODEL")

        return EmbeddingConfig(
            dim=dim,
            primary=primary,
            fallback=fallback,
            ollama_host=ollama_host,
            ollama_model=ollama_model,
            keep_alive=keep_alive,
            batch_size=batch_size,
            timeout_seconds=timeout_seconds,
            max_retries=max_retries,
            cf_account_id=cf_account_id,
            cf_api_token=cf_api_token,
            cf_model=cf_model,
        )


class EmbeddingError(RuntimeError):
    pass


# ---------------------------
# Helpers (trim/sanitize/cache)
# ---------------------------

def _trim_texts(texts: List[str]) -> List[str]:
    if EMBED_MAX_CHARS <= 0:
        return texts
    out = []
    for t in texts:
        t = t or ""
        out.append(t[:EMBED_MAX_CHARS] if len(t) > EMBED_MAX_CHARS else t)
    if len(out) != len(texts):
        # should never happen, but keep symmetry
        log.warning("embed.trim: output length mismatch (should not occur).")
    return out


def _sanitize_vec(vec: List[float]) -> List[float]:
    if any(
        (v is None or isinstance(v, bool) or math.isnan(v) or math.isinf(v))
        for v in vec
    ):
        raise EmbeddingError("Invalid number in embedding vector (NaN/Inf/None/bool).")
    return vec


def _cache_get(cache: Any, key: str) -> Optional[List[float]]:
    if cache is None:
        return None
    try:
        if hasattr(cache, "get"):
            return cache.get(key)
        return cache[key]  # type: ignore[index]
    except Exception:
        return None


def _cache_set(cache: Any, key: str, value: List[float]) -> None:
    if cache is None:
        return
    try:
        if hasattr(cache, "set"):
            cache.set(key, value)
        else:
            cache[key] = value  # type: ignore[index]
    except Exception:
        pass


# ---------------------------
# Embedder
# ---------------------------

class Embedder:
    """
    Async embedder:
      - Respects primary/fallback order.
      - Concurrent per-text for both backends (bounded by EMBED_CONCURRENCY).
      - Validates dimensions.
      - Optional cache: pass `ids` aligned with `texts` and a dict-like `cache`.
    """

    def __init__(self, cfg: EmbeddingConfig) -> None:
        self.cfg = cfg
        self.primary = cfg.primary
        self.fallback = cfg.fallback
        self._client: Optional[httpx.AsyncClient] = None
        self._ollama_url = f"{cfg.ollama_host}/api/embeddings" if cfg.ollama_host else None
        self._cf_url, self._cf_headers = self._build_cf(cfg)

        log.info(
            "embed.config dim=%s ollama_model=%s host=%s cf_model=%s retries=%s timeout_s=%s",
            cfg.dim, cfg.ollama_model, (cfg.ollama_host or ""), (cfg.cf_model or ""),
            cfg.max_retries, cfg.timeout_seconds,
        )

    # ---------- lifecycle ----------
    async def _client_get(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=self.cfg.timeout_seconds)
        return self._client

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    # ---------- public ----------
    async def embed(
        self,
        texts: List[str],
        *,
        ids: Optional[List[str]] = None,
        cache: Any = None,
    ) -> List[List[float]]:
        """
        Embed a list of texts.
        - Optional `ids` (same length as `texts`) enable cache short-circuiting.
        - `cache` can be a dict or object exposing get/set(key, value).
        """
        if not texts:
            return []

        # Trim overly long inputs defensively
        texts = _trim_texts(texts)

        # Try cache first (if provided and ids aligned)
        results: List[Optional[List[float]]] = [None] * len(texts)
        pending_indices: List[int] = list(range(len(texts)))
        if ids is not None and cache is not None and len(ids) == len(texts):
            hit = 0
            new_pending = []
            for i in pending_indices:
                vec = _cache_get(cache, ids[i])
                if vec is not None:
                    results[i] = _sanitize_vec(vec)
                    hit += 1
                else:
                    new_pending.append(i)
            pending_indices = new_pending
            if hit:
                log.info("embed.cache hits=%s miss=%s total=%s", hit, len(pending_indices), len(texts))
        else:
            log.info("embed.cache disabled (ids or cache not provided/aligned)")

        if not pending_indices:
            # All hits
            return [results[i] for i in range(len(results))]  # type: ignore[list-item]

        conc = self._embed_concurrency()
        log.info("embed.start to_embed=%s dim_expected=%s concurrency=%s", len(pending_indices), self.cfg.dim, conc)

        t0_all = time.time()
        order = self._backend_order()
        last_error: Optional[Exception] = None

        # Build a compact list of texts to embed this round
        pending_texts = [texts[i] for i in pending_indices]

        for backend in order:
            t0 = time.time()
            try:
                if backend == "ollama":
                    if not self._ollama_url:
                        raise EmbeddingError("Ollama not configured (missing host).")
                    log.info("embed.backend=ollama model=%s url=%s", self.cfg.ollama_model, self._ollama_url)
                    vecs = await self._embed_ollama(pending_texts, conc)
                else:
                    if not (self._cf_url and self._cf_headers and self.cfg.cf_model):
                        raise EmbeddingError("Cloudflare not configured (account_id/api_token/model).")
                    log.info("embed.backend=cloudflare model=%s url=%s", self.cfg.cf_model, self._cf_url)
                    vecs = await self._embed_cloudflare(pending_texts, conc)

                # sanitize + validate dim
                vecs = [_sanitize_vec(v) for v in vecs]
                self._validate(vecs, backend)

                # place into results and populate cache
                for j, idx in enumerate(pending_indices):
                    results[idx] = vecs[j]
                    if ids is not None and cache is not None:
                        _cache_set(cache, ids[idx], vecs[j])

                dur_ms = (time.time() - t0) * 1000.0
                log.info("embed.done backend=%s n=%s ms=%.1f", backend, len(pending_indices), dur_ms)
                break  # success → exit backend loop

            except Exception as e:
                last_error = e
                log.warning(
                    "embed.primary_failed backend=%s model=%s reason=%s",
                    backend,
                    (self.cfg.cf_model if backend == "cloudflare" else self.cfg.ollama_model),
                    e,
                )
                # try next backend (fallback) if any
                continue

        if any(v is None for v in results):
            # both primary and fallback failed for pending items
            raise EmbeddingError(str(last_error) if last_error else "Embedding failed")

        total_ms = (time.time() - t0_all) * 1000.0
        log.info("embed.total n=%s ms=%.1f backend_used=%s", len(texts), total_ms, (order[0] if results else "n/a"))
        return [results[i] for i in range(len(results))]  # type: ignore[list-item]

    # ---------- backend order ----------
    def _backend_order(self) -> List[str]:
        if self.fallback and self.fallback != self.primary:
            return [self.primary, self.fallback]
        return [self.primary]

    # ---------- concurrency ----------
    def _embed_concurrency(self) -> int:
        """
        Read EMBED_CONCURRENCY safely. Falls back to 4 on empty/invalid.
        """
        raw = os.getenv("EMBED_CONCURRENCY", "2").strip()
        try:
            return max(1, int(raw)) if raw else 4
        except ValueError:
            return 4

    # ---------- OLLAMA (concurrent per-text) ----------
    async def _embed_ollama(self, texts: List[str], concurrency: int) -> List[List[float]]:
        sem = asyncio.Semaphore(concurrency)
        results: List[Optional[List[float]]] = [None] * len(texts)

        async def run_one(idx: int, t: str):
            async with sem:
                if EMBED_PACING_MS:
                    await asyncio.sleep(EMBED_PACING_MS / 1000.0)
                log.info("ollama.req start idx=%s/%s", idx + 1, len(texts))
                ok, v_or_exc = await self._retry(self._ollama_one_once, t)
                if not ok:
                    log.error("ollama.req fail  idx=%s/%s err=%s", idx + 1, len(texts), v_or_exc)
                    raise EmbeddingError(f"Ollama(single) failed after retries: {v_or_exc}")
                results[idx] = v_or_exc
                log.info("ollama.req done  idx=%s/%s", idx + 1, len(texts))

        await asyncio.gather(*(run_one(i, t) for i, t in enumerate(texts)))
        return [v for v in results]  # type: ignore[return-value]

    async def _ollama_one_once(self, text: str) -> List[float]:
        """
        Single-item call using the reliable `prompt` schema,
        Accepts {"embedding":[...]} or {"embeddings":[[...]]} (len==1).
        """
        client = await self._client_get()
        payload = {"model": self.cfg.ollama_model, "prompt": text, "keep_alive": self.cfg.keep_alive}
        r = await client.post(self._ollama_url, json=payload)  # type: ignore[arg-type]
        r.raise_for_status()
        data = r.json()

        if "embedding" in data and isinstance(data["embedding"], list):
            return data["embedding"]
        if "embeddings" in data and isinstance(data["embeddings"], list) and len(data["embeddings"]) == 1:
            inner = data["embeddings"][0]
            if isinstance(inner, list):
                return inner
        raise EmbeddingError("Ollama(single): response missing 'embedding' or single 'embeddings' element.")

    # ---------- CLOUDFLARE (concurrent per-text) ----------
    async def _embed_cloudflare(self, texts: List[str], concurrency: int) -> List[List[float]]:
        if not (self._cf_url and self._cf_headers):
            raise EmbeddingError("Cloudflare config missing (account_id/api_token/model).")

        client = await self._client_get()
        sem = asyncio.Semaphore(concurrency)
        out: List[Optional[List[float]]] = [None] * len(texts)

        async def run_one(idx: int, t: str):
            async with sem:
                if EMBED_PACING_MS:
                    await asyncio.sleep(EMBED_PACING_MS / 1000.0)
                log.info("cf.req     start idx=%s/%s", idx + 1, len(texts))
                ok, vec_or_exc = await self._retry(self._cf_one_once, t, client)
                if not ok:
                    log.error("cf.req     fail  idx=%s/%s err=%s", idx + 1, len(texts), vec_or_exc)
                    raise EmbeddingError(f"Cloudflare(single) failed after retries: {vec_or_exc}")
                out[idx] = vec_or_exc
                log.info("cf.req     done  idx=%s/%s", idx + 1, len(texts))

        await asyncio.gather(*(run_one(i, t) for i, t in enumerate(texts)))
        return [v for v in out]  # type: ignore[return-value]

    async def _cf_one_once(self, text: str, client: httpx.AsyncClient) -> List[float]:
        """
        Cloudflare Workers AI embedding response (per docs):
        Single input returns: {"result": {"data": [[...]], "shape": [1, D], "pooling": "mean"}}
        Also tolerate older/alternate shapes:
        {"result": [floats...]}  or  {"result": {"embedding":[floats...]}}  or  {"result":{"data":{"data":[floats...],...}}}
        """
        r = await client.post(self._cf_url, headers=self._cf_headers, json={"text": text})  # type: ignore[arg-type]
        r.raise_for_status()
        root = r.json()
        res = root.get("result")

        # Normalize to a flat list[float]
        def _as_vector(x) -> Optional[List[float]]:
            # direct 1-D vector
            if isinstance(x, list) and x and all(isinstance(v, (int, float)) for v in x):
                return x
            # 2-D: [[...]] -> [...]
            if isinstance(x, list) and x and isinstance(x[0], list):
                inner = x[0]
                if all(isinstance(v, (int, float)) for v in inner):
                    return inner
            # dict form: {"data":[...]} or {"embedding":[...]} or {"data":{"data":[...]}}
            if isinstance(x, dict):
                cand = x.get("data") or x.get("embedding")
                if isinstance(cand, dict):
                    cand = cand.get("data")
                return _as_vector(cand)
            return None

        vec = _as_vector(res)
        if vec is None:
            from json import dumps
            raise EmbeddingError(f"Cloudflare: unexpected embedding shape: {dumps(root)[:300]}")

        return vec


    # ---------- utils ----------
    async def _retry(self, fn, *args, **kwargs) -> Tuple[bool, Any]:
        """
        Retry with exponential backoff + jitter.
        Honors 429 Retry-After and treats 408/429/5xx as retryable.
        """
        last_exc: Optional[Exception] = None
        for attempt in range(self.cfg.max_retries + 1):
            try:
                return True, await fn(*args, **kwargs)
            except asyncio.CancelledError:
                raise
            except Exception as e:
                last_exc = e
                if attempt >= self.cfg.max_retries:
                    break

                # Default backoff
                base = 0.8
                sleep = base * (2 ** attempt) + random.uniform(0, 0.25)

                # If HTTP error, tune by status and Retry-After
                if isinstance(e, HTTPStatusError):
                    code = e.response.status_code
                    if code == 429:
                        ra = e.response.headers.get("Retry-After")
                        if ra and ra.isdigit():
                            sleep = max(sleep, float(ra))
                        else:
                            sleep = max(sleep, 2.0)  # be gentler on 429
                    elif code in (408, 500, 502, 503, 504):
                        sleep = max(sleep, 1.0)

                log.warning("retrying (%d/%d) in %.2fs: %s", attempt + 1, self.cfg.max_retries, sleep, e)
                await asyncio.sleep(sleep)
        return False, last_exc


    def _validate(self, vecs: List[List[float]], backend: str) -> None:
        if not vecs:
            return
        d = len(vecs[0])
        if d != self.cfg.dim:
            log.error("embed.dim_mismatch observed=%s expected=%s backend=%s", d, self.cfg.dim, backend)
            raise EmbeddingError(
                f"Vector dim mismatch: backend={backend} dim={d}, expected={self.cfg.dim}. "
                "Adjust profile.embedding.dim or model."
            )

    @staticmethod
    def _build_cf(cfg: EmbeddingConfig) -> Tuple[Optional[str], Optional[Dict[str, str]]]:
        if cfg.cf_account_id and cfg.cf_api_token and cfg.cf_model:
            url = f"https://api.cloudflare.com/client/v4/accounts/{cfg.cf_account_id}/ai/run/{cfg.cf_model}"
            headers = {"Authorization": f"Bearer {cfg.cf_api_token}"}
            return url, headers
        return None, None


# ---------- convenience for ad-hoc tests ----------
async def demo_embed(texts: List[str], dim: int) -> Dict[str, Any]:
    """
    Ad-hoc helper (uses env OLLAMA_HOST/EMBED_MODEL/CF_*). Example in PowerShell:

      docker compose exec api python /app/src/tools/run_snippet.py `
        --module learning_mcp.embeddings `
        --call demo_embed `
        --kwargs '{"texts":["hello","world"],"dim":384}'
    """
    host = os.getenv("OLLAMA_HOST", "http://host.docker.internal:11434").rstrip("/")
    model = os.getenv("EMBED_MODEL", "nomic-embed-text")
    primary = os.getenv("EMBED_PRIMARY", "ollama")
    fallback = os.getenv("EMBED_FALLBACK", "")

    cfg = EmbeddingConfig(
        dim=dim,
        primary=primary,
        fallback=(fallback or None),
        ollama_host=host,
        ollama_model=model,
        keep_alive=os.getenv("EMBED_KEEP_ALIVE", "15m"),
        batch_size=int(os.getenv("EMBED_BATCH_SIZE", "32")),
        timeout_seconds=float(os.getenv("EMBED_TIMEOUT_SECONDS", "300")),
        max_retries=int(os.getenv("EMBED_MAX_RETRIES", "3")),
        cf_account_id=os.getenv("CF_ACCOUNT_ID"),
        cf_api_token=os.getenv("CF_API_TOKEN"),
        cf_model=os.getenv("CF_EMBED_MODEL"),
    )
    emb = Embedder(cfg)
    try:
        vecs = await emb.embed(texts)
        return {
            "count": len(vecs),
            "dims_expected": dim,
            "dim_actual": (len(vecs[0]) if vecs else 0),
            "primary": cfg.primary,
            "fallback": cfg.fallback,
        }
    finally:
        await emb.close()
