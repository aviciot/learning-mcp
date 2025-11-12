# Learning MCP V2.0 - Simplified RAG Server

**Status**: ✅ APPROVED - Ready for Implementation  
**Date**: November 11, 2025  
**Estimated Effort**: ~13 hours (2-3 days)

---

## User Decisions ✅

1. **Ingest**: ✅ On-demand only (via `ingest_profile` tool)
2. **Transport**: ✅ HTTP SSE (Server-Sent Events) - for MCP Inspector & remote clients
3. **AutoGen**: ✅ **Keep as 4th optional tool** - `plan_api_call` (controlled by `USE_AUTOGEN=1` env var)
4. **Test Coverage**: ✅ 80% for core modules (embeddings, vdb, loaders), 70% for mcp_server, 75% overall

---

## Vision

**From**: Monolithic FastAPI+MCP server with 10+ endpoints, complex routing, mixed concerns  
**To**: **Hybrid architecture** - fastmcp for MCP tools (search) + FastAPI for job management (ingest monitoring)

### Core Philosophy
- **Separation of concerns**: MCP for AI agent interactions, FastAPI for human/dashboard monitoring
- **Best of both worlds**: MCP-native search + robust background job tracking
- **Simplicity where it matters**: 3 MCP tools (~150 lines) + 4 job endpoints (~200 lines)
- **Optional complexity**: AutoGen available but disabled by default

---

## Architecture

### Technology Stack

```
┌──────────────────────────────────────────────────────────────┐
│                    Two-Server Architecture                    │
├──────────────────────────────────┬───────────────────────────┤
│   fastmcp Server (Port 8013)     │  FastAPI Server (8014)    │
│   MCP Tools for AI Agents        │  Job Management (HTTP)    │
└──────────────┬───────────────────┴───────────┬───────────────┘
               │                               │
    ┌──────────┴────────┬──────────────┬──────▼──────┬─────────┐
    │                   │              │             │         │
┌───▼────┐        ┌─────▼──────┐  ┌───▼──────┐  ┌──▼─────┐ ┌─▼────────┐
│ Embed  │        │    VDB     │  │  Loaders │  │ AutoGen│ │ Jobs DB  │
│ (dual) │        │  (Qdrant)  │  │(PDF/JSON)│  │(option)│ │ (SQLite) │
└────────┘        └────────────┘  └──────────┘  └────────┘ └──────────┘
```

### MCP Server (fastmcp - Port 8013)

**Purpose**: AI agent interactions via MCP protocol

| Tool | Purpose | Example Input |
|------|---------|---------------|
| `search_docs` | Semantic search over ingested docs | `{"q": "wifi settings", "profile": "dahua-camera", "top_k": 5}` |
| `list_profiles` | Show available profiles from YAML | `{}` |
| `plan_api_call` | AutoGen-powered API planning (optional) | `{"goal": "enable audio", "profile": "dahua-camera"}` |

| Resource | Purpose | Example |
|----------|---------|---------|
| `profile://{name}` | Get full YAML config for a profile | `profile://dahua-camera` |

### Job Server (FastAPI - Port 8014)

**Purpose**: Background job management and monitoring (HTTP REST)

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/ingest/jobs` | POST | Start background ingest job, returns job_id |
| `/ingest/cancel_all` | POST | Cancel all running ingest jobs |
| `/jobs` | GET | List all jobs (with filters: profile, status) |
| `/jobs/{job_id}` | GET | Get detailed job status with progress |
| `/health` | GET | Health check for job server |

**Why Keep FastAPI?**
- ✅ **Background jobs**: Non-blocking ingest with progress tracking
- ✅ **Cancellation**: Stop long-running embeds gracefully
- ✅ **Monitoring**: Dashboard-ready HTTP endpoints for job status
- ✅ **Existing code**: Leverage current job_manager.py + jobs_db.py with minimal changes
- ✅ **Human-friendly**: Swagger UI at `/docs` for manual testing

---

## File Structure Changes

### NEW FILES
```
src/
├─ mcp_server.py                          # NEW: fastmcp server (~150 lines, 3 tools)
├─ job_server.py                          # NEW: FastAPI job management (~200 lines)
└─ learning_mcp/
    └─ agents/
        └─ autogen_planner.py             # NEW: Refactored AutoGen logic (optional)

tests/
├─ test_mcp_tools.py                      # NEW: Integration tests (fastmcp in-memory client)
├─ test_job_api.py                        # NEW: FastAPI job endpoint tests
└─ test_core/
    ├─ test_embeddings.py                 # NEW: Unit tests for embeddings
    ├─ test_vdb.py                        # NEW: Unit tests for VDB
    └─ test_loaders.py                    # NEW: Unit tests for document loaders

.github/
└─ workflows/
    ├─ test.yml                           # NEW: CI - run tests on PR
    └─ docker-build.yml                   # NEW: Build & push to GHCR
```

### KEEP (Core Business Logic + Job Infrastructure)
```
src/learning_mcp/
├─ embeddings.py          # ✅ Dual backend (Ollama/Cloudflare)
├─ vdb.py                 # ✅ Qdrant wrapper with UUIDv5 IDs
├─ document_loaders.py    # ✅ Type-agnostic loader registry
├─ pdf_loader.py          # ✅ PDF loading via pypdf
├─ json_loader.py         # ✅ JSON loading
├─ chunker.py             # ✅ Text chunking logic
├─ config.py              # ✅ YAML profile loader
├─ page_ranges.py         # ✅ Page range parsing
├─ job_manager.py         # ✅ Background job orchestration (keep for job_server)
└─ jobs_db.py             # ✅ SQLite job tracking (keep for job_server)

config/learning.yaml      # ✅ Profile definitions
data/                     # ✅ Document storage
state/                    # ✅ SQLite database for job tracking
docker-compose.yml        # ⚠️ UPDATE for dual-server setup
Dockerfile                # ⚠️ UPDATE CMD to run both servers
pyproject.toml            # ⚠️ UPDATE dependencies
```

### REMOVE (Old Route Files)
```
❌ src/learning_mcp/app.py                # Replaced by mcp_server.py + job_server.py
❌ src/learning_mcp/routes/               # Most route files removed, consolidated
    ❌ api_agent.py                        # Replaced by MCP tool: plan_api_call
    ❌ api_plan.py                         # Replaced by MCP tool: plan_api_call
    ❌ api_exec.py                         # Remove (stub only)
    ❌ search_api.py                       # Replaced by MCP tool: search_docs
    ❌ search.py                           # Remove (legacy)
    ❌ config_route.py                     # Replaced by MCP resource: profile://
    ❌ echo.py                             # Remove (demo only)
    ❌ embed_health.py                     # Remove (use /health on job_server)
    ❌ embed_sample.py                     # Remove (debug endpoint)
    ❌ health.py                           # Keep logic, move to job_server.py
    ✅ ingest.py                           # KEEP - refactor into job_server.py
    ✅ jobs.py                             # KEEP - refactor into job_server.py
❌ src/learning_mcp/autogen_agent.py      # Refactored to agents/autogen_planner.py
❌ src/utils/inprocess_client.py          # Use fastmcp's Client
```

---

## Implementation Plan

### Phase 1A: MCP Server (~3 hours)

**File**: `src/mcp_server.py`

```python
"""Learning MCP V2.0 - MCP Server for AI Agent Interactions."""

import logging
import os
from typing import Optional

from fastmcp import FastMCP, Context

# Core logic imports
from learning_mcp.config import get_config, get_profile
from learning_mcp.embeddings import Embedder
from learning_mcp.vdb import VDB

log = logging.getLogger("learning_mcp.mcp_server")

# Initialize MCP server
mcp = FastMCP("learning-mcp-server", dependencies=["qdrant-client", "httpx", "pypdf"])

# Global state (lazy-loaded)
_embedder: Optional[Embedder] = None
_vdb: Optional[VDB] = None


def _get_embedder() -> Embedder:
    """Lazy-load embedder singleton."""
    global _embedder
    if _embedder is None:
        _embedder = Embedder()
    return _embedder


def _get_vdb() -> VDB:
    """Lazy-load VDB singleton."""
    global _vdb
    if _vdb is None:
        _vdb = VDB()
    return _vdb


@mcp.tool
async def search_docs(
    q: str,
    profile: str,
    top_k: int = 5,
    ctx: Context = None
) -> dict:
    """
    Semantic search over documents in a profile's collection.
    
    Args:
        q: Natural language query
        profile: Profile name (e.g., 'avi-cohen', 'dahua-camera')
        top_k: Number of results to return (default 5, max 20)
    
    Returns:
        dict with 'results' (list of scored chunks) and 'metadata'
    """
    if ctx:
        ctx.info(f"Searching profile '{profile}' for: {q[:50]}...")
    
    prof = get_profile(profile)
    embedder = _get_embedder()
    vdb = _get_vdb()
    
    # Embed query
    query_vec = await embedder.embed_single(q)
    
    # Search Qdrant
    collection = prof.vectordb.collection
    results = await vdb.search(
        collection=collection,
        query_vector=query_vec,
        limit=min(top_k, 20),
        score_threshold=prof.search.get("score_threshold", 0.5)
    )
    
    if ctx:
        ctx.info(f"Found {len(results)} results")
    
    return {
        "results": [
            {
                "text": r.payload.get("text"),
                "score": r.score,
                "metadata": {
                    "doc_id": r.payload.get("doc_id"),
                    "chunk_idx": r.payload.get("chunk_idx"),
                    "source": r.payload.get("doc_path")
                }
            }
            for r in results
        ],
        "metadata": {
            "profile": profile,
            "collection": collection,
            "top_k": top_k,
            "query": q
        }
    }


@mcp.tool
async def list_profiles() -> dict:
    """
    List all available profiles from learning.yaml.
    
    Returns:
        dict with 'profiles' list containing name, description, doc count
    """
    cfg = get_config()
    profiles = []
    
    for name, prof_data in cfg.profiles.items():
        profiles.append({
            "name": name,
            "description": prof_data.get("description", ""),
            "document_count": len(prof_data.get("documents", [])),
            "embedding_backend": prof_data.get("embedding", {}).get("backend", {}).get("primary", "unknown"),
            "collection": prof_data.get("vectordb", {}).get("collection", name)
        })
    
    return {"profiles": profiles}


@mcp.tool
async def plan_api_call(
    goal: str,
    profile: str,
    ctx: Context = None
) -> dict:
    """
    Use AutoGen to plan an API call based on documentation search.
    OPTIONAL: Only available if USE_AUTOGEN=1 env var is set.
    
    Args:
        goal: What you want to accomplish (e.g., "enable wifi on camera")
        profile: Profile to search for API docs
    
    Returns:
        dict with 'method', 'endpoint', 'params', 'reasoning'
    """
    if not os.getenv("USE_AUTOGEN", "0") == "1":
        return {
            "status": "disabled",
            "message": "AutoGen is disabled. Set USE_AUTOGEN=1 to enable API planning."
        }
    
    # Lazy import (optional dependency)
    try:
        from learning_mcp.agents.autogen_planner import plan_with_autogen
    except ImportError:
        return {
            "status": "not_installed",
            "message": "AutoGen dependencies not installed. Run: pip install pyautogen"
        }
    
    if ctx:
        ctx.info(f"Planning API call for goal: {goal}")
    
    # Search for relevant docs
    search_results = await search_docs(q=goal, profile=profile, top_k=10, ctx=ctx)
    
    # Use AutoGen planner
    plan = await plan_with_autogen(
        goal=goal,
        context_chunks=[r["text"] for r in search_results["results"]],
        profile=profile
    )
    
    if ctx:
        ctx.info(f"Generated plan: {plan.get('endpoint', 'N/A')}")
    
    return plan


@mcp.resource("profile://{name}")
async def get_profile_config(name: str) -> str:
    """
    Get full YAML configuration for a specific profile.
    
    Args:
        name: Profile name
    
    Returns:
        YAML string of profile config
    """
    import yaml
    prof = get_profile(name)
    return yaml.dump(prof, default_flow_style=False)


if __name__ == "__main__":
    # Run with HTTP SSE transport (for MCP Inspector, remote clients)
    # For Claude Desktop with stdio, use: fastmcp run src/mcp_server.py
    transport = os.getenv("MCP_TRANSPORT", "sse")
    
    if transport == "sse":
        log.info("Starting MCP server with HTTP SSE transport on port 8013")
        mcp.run(transport="sse", host="0.0.0.0", port=int(os.getenv("MCP_PORT", 8013)))
    else:
        log.info("Starting MCP server with stdio transport")
        mcp.run(transport="stdio")
```

**Tasks:**
1. Create `src/mcp_server.py` with above code
2. Test locally: `python src/mcp_server.py`
3. Verify tools: Connect with MCP Inspector

**Time**: ~3 hours

---

### Phase 1B: Job Server (~3 hours)

**File**: `src/job_server.py`

```python
"""Learning MCP V2.0 - FastAPI Job Management Server."""

import logging
import os
from typing import List, Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

# Reuse existing job infrastructure
from learning_mcp.job_manager import JobManager
from learning_mcp.jobs_db import JobsDB, JobStatus

log = logging.getLogger("learning_mcp.job_server")

# Initialize FastAPI
app = FastAPI(
    title="Learning MCP - Job Management",
    description="Background job tracking for document ingestion",
    version="2.0.0"
)

# CORS for web dashboards
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global job manager
_job_manager: Optional[JobManager] = None


def _get_job_manager() -> JobManager:
    """Lazy-load job manager singleton."""
    global _job_manager
    if _job_manager is None:
        _job_manager = JobManager()
    return _job_manager


# ---------- Schemas ----------

class IngestRequest(BaseModel):
    profile: str = Field(..., example="dahua-camera")
    truncate: bool = Field(False, description="Clear collection before ingest")


class IngestResponse(BaseModel):
    job_id: str
    profile: str
    status: str
    message: str


class JobBrief(BaseModel):
    job_id: str
    profile: str
    status: str
    phase: str
    pages_done: int
    pages_total: int
    pct: int


class JobDetail(BaseModel):
    job_id: str
    profile: str
    status: str
    phase: str
    pages_done: int
    pages_total: int
    files_done: int
    files_total: int
    chunks_upserted: int
    error_msg: Optional[str]
    started_at: Optional[str]
    finished_at: Optional[str]


# ---------- Endpoints ----------

@app.post("/ingest/jobs", response_model=IngestResponse, tags=["Ingest"])
async def start_ingest_job(req: IngestRequest):
    """
    Start a background ingest job for a profile.
    
    Returns job_id immediately, job runs asynchronously.
    """
    job_mgr = _get_job_manager()
    
    try:
        job_id = await job_mgr.enqueue_ingest(
            profile=req.profile,
            truncate=req.truncate
        )
        
        return IngestResponse(
            job_id=job_id,
            profile=req.profile,
            status="queued",
            message=f"Ingest job started for profile '{req.profile}'"
        )
    except Exception as e:
        log.error(f"Failed to start ingest: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/ingest/cancel_all", tags=["Ingest"])
async def cancel_all_jobs():
    """
    Cancel all running ingest jobs.
    """
    job_mgr = _get_job_manager()
    cancelled = await job_mgr.cancel_all()
    
    return {
        "status": "ok",
        "cancelled_count": cancelled,
        "message": f"Cancelled {cancelled} running jobs"
    }


@app.get("/jobs", response_model=List[JobBrief], tags=["Jobs"])
async def list_jobs(
    profile: Optional[str] = Query(None, description="Filter by profile"),
    status: Optional[str] = Query(None, description="Filter by status"),
    limit: int = Query(20, ge=1, le=100)
):
    """
    List recent jobs with optional filters.
    """
    db = JobsDB()
    jobs = db.list_jobs(profile=profile, status=status, limit=limit)
    
    return [
        JobBrief(
            job_id=j["job_id"],
            profile=j["profile"],
            status=j["status"],
            phase=j["phase"],
            pages_done=j["pages_done"],
            pages_total=j["pages_total"],
            pct=j["pct"]
        )
        for j in jobs
    ]


@app.get("/jobs/{job_id}", response_model=JobDetail, tags=["Jobs"])
async def get_job_detail(job_id: str):
    """
    Get detailed status for a specific job.
    """
    db = JobsDB()
    job = db.get_job(job_id)
    
    if not job:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")
    
    return JobDetail(
        job_id=job["job_id"],
        profile=job["profile"],
        status=job["status"],
        phase=job["phase"],
        pages_done=job["pages_done"],
        pages_total=job["pages_total"],
        files_done=job["files_done"],
        files_total=job["files_total"],
        chunks_upserted=job["chunks_upserted"],
        error_msg=job.get("error_msg"),
        started_at=job.get("started_at"),
        finished_at=job.get("finished_at")
    )


@app.get("/health", tags=["Health"])
async def health_check():
    """
    Health check endpoint.
    """
    return {
        "status": "ok",
        "service": "job-server",
        "version": "2.0.0"
    }


if __name__ == "__main__":
    import uvicorn
    
    port = int(os.getenv("JOB_PORT", 8014))
    
    log.info(f"Starting Job Server on port {port}")
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=port,
        log_level="info"
    )
```

**Tasks:**
1. Create `src/job_server.py` with above code
2. Refactor `job_manager.py` if needed (extract background worker logic)
3. Test: `python src/job_server.py`
4. Verify endpoints: `curl http://localhost:8014/health`

**Time**: ~3 hours

---

### Phase 2: Testing (~3 hours)

#### 2.1 MCP Integration Tests

**File**: `tests/test_mcp_tools.py`

```python
"""Integration tests for MCP tools using fastmcp's in-memory client."""

import pytest
from fastmcp import Client

# Import the mcp server instance
from mcp_server import mcp


@pytest.mark.asyncio
async def test_list_profiles():
    """Test list_profiles tool returns expected profiles."""
    async with Client(mcp) as client:
        result = await client.call_tool("list_profiles", arguments={})
        
        assert "profiles" in result
        assert len(result["profiles"]) > 0
        assert any(p["name"] == "avi-cohen" for p in result["profiles"])


@pytest.mark.asyncio
async def test_search_docs_requires_ingest():
    """Test search_docs on empty collection."""
    async with Client(mcp) as client:
        result = await client.call_tool(
            "search_docs",
            arguments={"q": "test", "profile": "avi-cohen", "top_k": 5}
        )
        
        # Should return empty results or error
        assert "results" in result or "error" in result


@pytest.mark.asyncio
async def test_ingest_then_search():
    """Full workflow: ingest → search."""
    async with Client(mcp) as client:
        # 1. Ingest
        ingest_result = await client.call_tool(
            "ingest_profile",
            arguments={"profile": "avi-cohen", "truncate": True}
        )
        
        assert ingest_result["status"] == "success"
        assert ingest_result["chunks_ingested"] > 0
        
        # 2. Search
        search_result = await client.call_tool(
            "search_docs",
            arguments={"q": "Python experience", "profile": "avi-cohen", "top_k": 3}
        )
        
        assert "results" in search_result
        assert len(search_result["results"]) > 0
        assert search_result["results"][0]["score"] > 0.5


@pytest.mark.asyncio
async def test_plan_api_call_disabled_by_default():
    """Test plan_api_call returns disabled message when USE_AUTOGEN=0."""
    async with Client(mcp) as client:
        result = await client.call_tool(
            "plan_api_call",
            arguments={"goal": "enable wifi", "profile": "dahua-camera"}
        )
        
        assert result["status"] == "disabled"
        assert "USE_AUTOGEN=1" in result["message"]


@pytest.mark.asyncio
async def test_profile_resource():
    """Test profile:// resource."""
    async with Client(mcp) as client:
        result = await client.read_resource("profile://avi-cohen")
        
        assert "embedding:" in result  # YAML content
        assert "vectordb:" in result
```

#### 2.2 Core Unit Tests

**File**: `tests/test_job_api.py`

```python
"""Integration tests for Job Server FastAPI endpoints."""

import pytest
from fastapi.testclient import TestClient

from job_server import app

client = TestClient(app)


def test_health_check():
    """Test health endpoint returns 200."""
    response = client.get("/health")
    
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.json()["service"] == "job-server"


def test_list_jobs():
    """Test listing jobs."""
    response = client.get("/jobs")
    
    assert response.status_code == 200
    assert "jobs" in response.json() or isinstance(response.json(), list)


def test_list_jobs_with_filters():
    """Test listing jobs with profile filter."""
    response = client.get("/jobs?profile=avi-cohen&limit=5")
    
    assert response.status_code == 200


def test_start_ingest_job():
    """Test starting an ingest job."""
    response = client.post(
        "/ingest/jobs",
        json={"profile": "avi-cohen", "truncate": False}
    )
    
    assert response.status_code == 200
    assert "job_id" in response.json()
    assert response.json()["profile"] == "avi-cohen"
    assert response.json()["status"] in ["queued", "running"]


def test_get_job_detail():
    """Test getting job detail by ID."""
    # First create a job
    create_response = client.post(
        "/ingest/jobs",
        json={"profile": "avi-cohen", "truncate": False}
    )
    job_id = create_response.json()["job_id"]
    
    # Then get its details
    detail_response = client.get(f"/jobs/{job_id}")
    
    assert detail_response.status_code == 200
    assert detail_response.json()["job_id"] == job_id


def test_cancel_all_jobs():
    """Test cancelling all jobs."""
    response = client.post("/ingest/cancel_all")
    
    assert response.status_code == 200
    assert "cancelled_count" in response.json()


def test_get_nonexistent_job():
    """Test getting a job that doesn't exist."""
    response = client.get("/jobs/nonexistent-job-id")
    
    assert response.status_code == 404
```

#### 2.3 Core Unit Tests

**File**: `tests/test_core/test_embeddings.py`

```python
"""Unit tests for embeddings module - TARGET: 80% coverage."""

import pytest
from learning_mcp.embeddings import Embedder, EmbeddingError


@pytest.mark.asyncio
async def test_embed_single_text():
    """Test embedding a single text."""
    embedder = Embedder()
    result = await embedder.embed_single("test text")
    
    assert isinstance(result, list)
    assert len(result) > 0
    assert all(isinstance(x, float) for x in result)


@pytest.mark.asyncio
async def test_embed_multiple_texts():
    """Test embedding multiple texts concurrently."""
    embedder = Embedder()
    texts = ["first", "second", "third"]
    
    results = await embedder.embed(texts)
    
    assert len(results) == 3
    assert all(len(vec) == len(results[0]) for vec in results)


@pytest.mark.asyncio
async def test_embed_with_cache():
    """Test caching behavior."""
    embedder = Embedder()
    cache = {}
    texts = ["cached text", "cached text"]  # duplicate
    ids = ["id1", "id2"]
    
    results = await embedder.embed(texts, ids=ids, cache=cache)
    
    assert len(cache) == 1  # Only one unique text cached
    assert "id1" in cache or "id2" in cache


@pytest.mark.asyncio
async def test_dimension_validation():
    """Test dimension mismatch detection."""
    embedder = Embedder()
    embedder.expected_dim = 9999  # Set invalid dimension
    
    with pytest.raises(EmbeddingError, match="dimension mismatch"):
        await embedder.embed_single("test")
```

**File**: `tests/test_core/test_vdb.py`

```python
"""Unit tests for VDB module - TARGET: 80% coverage."""

import pytest
from learning_mcp.vdb import VDB


@pytest.fixture
def vdb():
    """Create VDB instance for testing."""
    return VDB()


@pytest.mark.asyncio
async def test_ensure_collection_creates_new(vdb):
    """Test creating a new collection."""
    test_collection = "test_col_new"
    
    await vdb.ensure_collection(test_collection, dim=384)
    
    collections = await vdb.list_collections()
    assert test_collection in collections


@pytest.mark.asyncio
async def test_upsert_and_search(vdb):
    """Test upserting points and searching."""
    test_collection = "test_col_search"
    await vdb.ensure_collection(test_collection, dim=3)
    
    # Upsert test point
    points = [{
        "id": "test-id-1",
        "vector": [0.1, 0.2, 0.3],
        "payload": {"text": "test content"}
    }]
    await vdb.upsert(test_collection, points)
    
    # Search
    results = await vdb.search(
        collection=test_collection,
        query_vector=[0.1, 0.2, 0.3],
        limit=1
    )
    
    assert len(results) == 1
    assert results[0].payload["text"] == "test content"


@pytest.mark.asyncio
async def test_delete_collection(vdb):
    """Test deleting a collection."""
    test_collection = "test_col_delete"
    await vdb.ensure_collection(test_collection, dim=384)
    
    await vdb.delete_collection(test_collection)
    
    collections = await vdb.list_collections()
    assert test_collection not in collections
```

**File**: `tests/test_core/test_loaders.py`

```python
"""Unit tests for document loaders - TARGET: 80% coverage."""

import pytest
from pathlib import Path
from learning_mcp.document_loaders import load_documents_from_profile
from learning_mcp.pdf_loader import load_pdf
from learning_mcp.json_loader import load_json


def test_load_pdf():
    """Test PDF loading."""
    # Assumes test PDF exists
    test_pdf = Path("tests/fixtures/sample.pdf")
    
    if not test_pdf.exists():
        pytest.skip("Test PDF not found")
    
    chunks = load_pdf(str(test_pdf))
    
    assert len(chunks) > 0
    assert all("text" in c and "metadata" in c for c in chunks)


def test_load_json():
    """Test JSON loading."""
    test_json = Path("tests/fixtures/sample.json")
    
    if not test_json.exists():
        pytest.skip("Test JSON not found")
    
    chunks = load_json(str(test_json))
    
    assert len(chunks) > 0
    assert all("text" in c and "metadata" in c for c in chunks)


@pytest.mark.asyncio
async def test_load_documents_from_profile():
    """Test loading all documents from a profile."""
    # Mock profile
    profile = {
        "name": "test-profile",
        "documents": [
            {"type": "json", "path": "data/persons/avi_profile.json"}
        ],
        "chunking": {"size": 1000, "overlap": 100}
    }
    
    chunks = await load_documents_from_profile(profile)
    
    assert len(chunks) > 0
```

**Tasks:**
1. Create `tests/` directory with all test files
2. Add test fixtures: `tests/fixtures/sample.pdf`, `tests/fixtures/sample.json`
3. Install pytest: `pip install pytest pytest-asyncio pytest-cov`
4. Run tests: `pytest tests/ -v --cov=learning_mcp --cov-report=term-missing`
5. Verify coverage: ≥80% for core modules

**Coverage Targets:**
- `embeddings.py`: 80%+
- `vdb.py`: 80%+
- `document_loaders.py`: 80%+
- `mcp_server.py`: 70%+ (some tools need live services)
- **Overall**: 75%+

**Time**: ~3 hours

---

### Phase 3: Docker Configuration (~2 hours)

#### 3.1 Update Dockerfile

**File**: `Dockerfile`

```dockerfile
FROM python:3.12-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    curl \
    supervisor \
    && rm -rf /var/lib/apt/lists/*

# Copy dependency files
COPY pyproject.toml ./

# Install Python dependencies
RUN pip install --no-cache-dir -e .

# Copy source code
COPY src/ ./src/
COPY config/ ./config/
COPY data/ ./data/

# Create state directory for SQLite
RUN mkdir -p /app/state

# Copy supervisor config for running both servers
COPY docker/supervisord.conf /etc/supervisor/conf.d/supervisord.conf

# Environment defaults
ENV PYTHONUNBUFFERED=1 \
    MCP_TRANSPORT=sse \
    MCP_PORT=8013 \
    JOB_PORT=8014 \
    USE_AUTOGEN=0

# Expose both ports
EXPOSE 8013 8014

# Run both servers via supervisor
CMD ["/usr/bin/supervisord", "-c", "/etc/supervisor/conf.d/supervisord.conf"]
```

#### 3.2 Create Supervisor Config

**File**: `docker/supervisord.conf`

```ini
[supervisord]
nodaemon=true
logfile=/dev/stdout
logfile_maxbytes=0

[program:mcp_server]
command=python src/mcp_server.py
directory=/app
autostart=true
autorestart=true
stdout_logfile=/dev/stdout
stdout_logfile_maxbytes=0
stderr_logfile=/dev/stderr
stderr_logfile_maxbytes=0

[program:job_server]
command=python src/job_server.py
directory=/app
autostart=true
autorestart=true
stdout_logfile=/dev/stdout
stdout_logfile_maxbytes=0
stderr_logfile=/dev/stderr
stderr_logfile_maxbytes=0
```

#### 3.3 Update docker-compose.yml

**File**: `docker-compose.yml`

```yaml
version: '3.8'

services:
  qdrant:
    image: qdrant/qdrant:latest
    ports:
      - "6333:6333"
    volumes:
      - ./qdrant_storage:/qdrant/storage
    networks:
      - learning-mcp-net

  learning-mcp:
    build: .
    ports:
      - "8013:8013"  # MCP server (SSE)
      - "8014:8014"  # Job server (HTTP REST)
    environment:
      - MCP_TRANSPORT=sse
      - MCP_PORT=8013
      - JOB_PORT=8014
      - VECTOR_DB_URL=http://qdrant:6333
      - OLLAMA_HOST=http://host.docker.internal:11434
      - USE_AUTOGEN=0
    env_file:
      - .env
    volumes:
      - ./src:/app/src:ro
      - ./config:/app/config:ro
      - ./data:/app/data:ro
      - ./state:/app/state  # Read-write for SQLite
    depends_on:
      - qdrant
    networks:
      - learning-mcp-net
    restart: unless-stopped

networks:
  learning-mcp-net:
    driver: bridge
```

**Tasks:**
1. Create `docker/supervisord.conf`
2. Update `Dockerfile` 
3. Update `docker-compose.yml`
4. Test: `docker compose up --build`
5. Verify both servers:
   - MCP: `curl http://localhost:8013/sse`
   - Jobs: `curl http://localhost:8014/health`

**Time**: ~2 hours

---

### Phase 4: GitHub Actions (~3 hours)

#### 4.1 CI Workflow (Tests)

**File**: `.github/workflows/test.yml`

```yaml
name: Run Tests

on:
  pull_request:
    branches: [main, develop]
  push:
    branches: [main, develop]

jobs:
  test:
    runs-on: ubuntu-latest
    
    services:
      qdrant:
        image: qdrant/qdrant:latest
        ports:
          - 6333:6333
    
    steps:
      - uses: actions/checkout@v4
      
      - name: Set up Python 3.12
        uses: actions/setup-python@v5
        with:
          python-version: '3.12'
      
      - name: Install dependencies
        run: |
          pip install -e .
          pip install pytest pytest-asyncio pytest-cov
      
      - name: Run tests with coverage
        env:
          VECTOR_DB_URL: http://localhost:6333
          OLLAMA_HOST: http://localhost:11434
        run: |
          pytest tests/ -v --cov=learning_mcp --cov-report=term-missing --cov-report=xml
      
      - name: Check coverage threshold
        run: |
          coverage report --fail-under=75
      
      - name: Upload coverage to Codecov (optional)
        uses: codecov/codecov-action@v3
        with:
          file: ./coverage.xml
          fail_ci_if_error: false
```

#### 4.2 Docker Build & Push

**File**: `.github/workflows/docker-build.yml`

```yaml
name: Build and Push Docker Image

on:
  push:
    branches: [main]
    tags: ['v*']
  workflow_dispatch:

env:
  REGISTRY: ghcr.io
  IMAGE_NAME: ${{ github.repository }}

jobs:
  build-and-push:
    runs-on: ubuntu-latest
    permissions:
      contents: read
      packages: write
    
    steps:
      - uses: actions/checkout@v4
      
      - name: Log in to GitHub Container Registry
        uses: docker/login-action@v3
        with:
          registry: ${{ env.REGISTRY }}
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}
      
      - name: Extract metadata
        id: meta
        uses: docker/metadata-action@v5
        with:
          images: ${{ env.REGISTRY }}/${{ env.IMAGE_NAME }}
          tags: |
            type=ref,event=branch
            type=semver,pattern={{version}}
            type=semver,pattern={{major}}.{{minor}}
            type=sha,prefix={{branch}}-
      
      - name: Build and push Docker image
        uses: docker/build-push-action@v5
        with:
          context: .
          push: true
          tags: ${{ steps.meta.outputs.tags }}
          labels: ${{ steps.meta.outputs.labels }}
      
      - name: Image digest
        run: echo ${{ steps.meta.outputs.digest }}
```

**Tasks:**
1. Create both workflow files
2. Push to GitHub (triggers workflows)
3. Fix any failing tests
4. Verify Docker image published to GHCR

**Time**: ~3 hours

---

## Migration Steps

### Step 1: Backup Current State
```powershell
git checkout -b v2-fastmcp-migration
git add -A
git commit -m "Checkpoint before V2 migration"
```

### Step 2: Implement Phase 1 (Core Server)
```powershell
# Create new MCP server
New-Item -Path "src\mcp_server.py" -ItemType File

# Copy code from Phase 1 section above

# Refactor AutoGen (optional)
New-Item -Path "src\learning_mcp\agents" -ItemType Directory
Move-Item "src\learning_mcp\autogen_agent.py" "src\learning_mcp\agents\autogen_planner.py"

# Test locally
docker compose down
docker compose up --build
```

### Step 3: Implement Phase 2 (Tests)
```powershell
# Create test structure
New-Item -Path "tests" -ItemType Directory
New-Item -Path "tests\test_core" -ItemType Directory
New-Item -Path "tests\fixtures" -ItemType Directory

# Create test files (copy from Phase 2)

# Run tests
docker compose exec learning-mcp pytest tests/ -v --cov=learning_mcp
```

### Step 4: Implement Phase 3 (Docker)
```powershell
# Update Dockerfile (copy from Phase 3)
# Update docker-compose.yml (copy from Phase 3)

# Rebuild and test
docker compose down
docker compose up --build

# Verify SSE endpoint
curl http://localhost:8013/sse
```

### Step 5: Implement Phase 4 (CI/CD)
```powershell
# Create workflows
New-Item -Path ".github\workflows" -ItemType Directory -Force
# Copy test.yml and docker-build.yml

# Push to GitHub
git add -A
git commit -m "V2: fastmcp migration complete"
git push origin v2-fastmcp-migration

# Create PR, verify CI passes
```

### Step 6: Clean Up Old Code
```powershell
# After V2 is verified working, remove old files
Remove-Item -Recurse -Force "src\learning_mcp\routes"
Remove-Item "src\learning_mcp\app.py"
Remove-Item "src\learning_mcp\job_manager.py"
Remove-Item "src\learning_mcp\jobs_db.py"
Remove-Item -Recurse -Force "src\utils"
Remove-Item -Recurse -Force "state"

git add -A
git commit -m "Remove legacy FastAPI code"
```

---

## Timeline

| Phase | Task | Hours | Day |
|-------|------|-------|-----|
| 1A | MCP Server | 3 | Day 1 |
| 1B | Job Server | 3 | Day 1 |
| 2 | Testing | 3 | Day 2 |
| 3 | Docker Config | 2 | Day 2 |
| 4 | GitHub Actions | 3 | Day 3 |
| **Total** | | **14** | **2-3 days** |

---

## Testing Checklist

**MCP Server (Port 8013):**
- [ ] All 3 MCP tools callable via fastmcp Client
- [ ] `list_profiles` returns avi-cohen, dahua-camera, etc.
- [ ] `search_docs` returns relevant results after ingest
- [ ] `plan_api_call` returns "disabled" when USE_AUTOGEN=0
- [ ] `plan_api_call` works when USE_AUTOGEN=1 (if installed)
- [ ] `profile://` resource returns YAML config
- [ ] HTTP SSE transport accessible at http://localhost:8013/sse
- [ ] MCP Inspector can connect and list tools

**Job Server (Port 8014):**
- [ ] `POST /ingest/jobs` starts background job, returns job_id
- [ ] `GET /jobs` lists jobs with filters (profile, status)
- [ ] `GET /jobs/{job_id}` returns detailed status with progress
- [ ] `POST /ingest/cancel_all` cancels running jobs
- [ ] `GET /health` returns 200 OK
- [ ] Swagger UI accessible at http://localhost:8014/docs
- [ ] SQLite database tracks job progress in `state/` directory

**Integration:**
- [ ] Job server can ingest → MCP server can search results
- [ ] Both servers run simultaneously in Docker
- [ ] Unit tests pass with ≥75% overall coverage
- [ ] Core modules (embeddings, vdb, loaders) ≥80% coverage
- [ ] GitHub Actions CI passes on PR
- [ ] Docker image builds and publishes to GHCR

---

## Success Criteria

✅ **Hybrid Architecture**: MCP for AI agents (3 tools, ~150 lines) + FastAPI for job management (4 endpoints, ~200 lines)  
✅ **Separation of Concerns**: Clean split between MCP interactions and background job tracking  
✅ **Background Jobs**: Non-blocking ingest with progress monitoring and cancellation  
✅ **Testable**: 75%+ overall coverage, 80%+ for core modules  
✅ **Automated**: CI runs tests on every PR, Docker builds on main push  
✅ **Optional Complexity**: AutoGen available but disabled by default  
✅ **HTTP SSE**: MCP server supports remote clients and MCP Inspector  
✅ **Dashboard-Ready**: Job server with Swagger UI for human monitoring  

---

## Next Steps After V2

- [ ] Add more document types (CSV, Markdown, HTML)
- [ ] Implement multi-modal embeddings (text + images)
- [ ] Add citation extraction to search results
- [ ] Expand AutoGen to execute API calls (not just plan)
- [ ] Add semantic caching layer for frequently asked questions
- [ ] Implement streaming search results for large result sets
- [ ] Add monitoring/observability (Prometheus metrics)

---

**Questions?** Review this spec, then proceed with Phase 1 implementation.
