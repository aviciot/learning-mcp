# Learning MCP - V2.0 Simplified Specification

**Date**: November 11, 2025  
**Branch**: MCP-search+execute(stub)-ready → `v2-fastmcp-simplified`  
**Goal**: Rebuild as a clean, simple MCP server using `fastmcp` library focusing on core RAG functionality

---

## Vision: Back to Basics

**Core Purpose**: RAG server for PDF/JSON documents with semantic search - nothing more.

### What We're Building
A simple MCP server that:
1. ✅ Loads documents from `config/learning.yaml` profiles
2. ✅ Embeds documents (Ollama/Cloudflare)
3. ✅ Stores vectors in Qdrant
4. ✅ Performs semantic search
5. ✅ Exposes via MCP protocol using `fastmcp`

### What We're Removing
- ❌ FastAPI (too complex for MCP-first approach)
- ❌ Swagger UI (not needed for MCP)
- ❌ Background job system (ingest on demand or startup)
- ❌ SQLite job tracking (keep it simple)
- ❌ AutoGen integration (add later if needed)
- ❌ API planning features (future iteration)
- ❌ Multiple redundant endpoints

---

## New Architecture (fastmcp-based)

### Technology Stack
```
fastmcp (MCP server framework)
    ↓
├─ Tools (3 simple MCP tools)
│   ├─ search_docs
│   ├─ ingest_profile  
│   └─ list_profiles
│
├─ Resources (profile information)
│   └─ profile://{name}
│
└─ Core Logic (keep existing, reuse)
    ├─ embeddings.py
    ├─ vdb.py
    ├─ document_loaders.py
    ├─ chunker.py
    └─ config.py (reads learning.yaml)
```

### Why fastmcp?
1. **Pure MCP protocol** - no HTTP abstraction needed
2. **Simpler than fastapi-mcp** - direct tool decoration
3. **Built-in testing** - in-memory client for tests
4. **Standard framework** - official MCP SDK integration
5. **Production-ready** - used by thousands of developers

---

## Design Decisions

---

## Design Decisions

### Decision 1: Use fastmcp (Pure MCP)
**Rationale**: MCP-first, not web-first. Claude Desktop and other MCP clients are the primary interface.

- ✅ **stdio transport** - standard for MCP (Claude Desktop default)
- ✅ **HTTP transport optional** - for testing/debugging only
- ✅ **No FastAPI dependency** - simpler, focused
- ✅ **Direct tool decoration** - `@mcp.tool` is all you need

### Decision 2: Three Core MCP Tools

| Tool | Purpose | Input | Output |
|------|---------|-------|--------|
| `search_docs` | Semantic search | `{"q": "wifi", "profile": "dahua-camera", "top_k": 5}` | List of scored chunks |
| `ingest_profile` | Load/embed documents | `{"profile": "dahua-camera", "truncate": false}` | Status message |
| `list_profiles` | Show available profiles | `{}` | List of profile names + stats |

### Decision 3: One Resource Template

| Resource | Purpose | Example |
|----------|---------|---------|
| `profile://{name}` | Get profile config | `profile://dahua-camera` |

### Decision 4: Keep Core Business Logic

**Reuse (no changes):**
- ✅ `embeddings.py` - dual backend (Ollama/Cloudflare)
- ✅ `vdb.py` - Qdrant wrapper
- ✅ `document_loaders.py` - PDF/JSON loading
- ✅ `chunker.py` - text chunking
- ✅ `config.py` - YAML profile loading

**Remove:**
- ❌ All `routes/` files
- ❌ `app.py` (replaced by `mcp_server.py`)
- ❌ `jobs_db.py`, `job_manager.py`
- ❌ `autogen_agent.py` (save for v3)
- ❌ `utils/inprocess_client.py`

---

## New File Structure

```
learning-mcp/
├─ src/
│   ├─ mcp_server.py           # NEW: Main fastmcp server (150 lines)
│   ├─ learning_mcp/
│   │   ├─ core/               # RENAMED from learning_mcp/
│   │   │   ├─ embeddings.py   # Keep
│   │   │   ├─ vdb.py          # Keep
│   │   │   ├─ document_loaders.py  # Keep
│   │   │   ├─ chunker.py      # Keep
│   │   │   ├─ config.py       # Keep
│   │   │   ├─ pdf_loader.py   # Keep
│   │   │   ├─ json_loader.py  # Keep
│   │   │   └─ page_ranges.py  # Keep
│   │   └─ __init__.py
├─ tests/
│   ├─ test_mcp_tools.py       # NEW: MCP tool tests
│   ├─ test_core/              # NEW: Unit tests for core
│   │   ├─ test_embeddings.py
│   │   ├─ test_vdb.py
│   │   └─ test_loaders.py
├─ config/
│   └─ learning.yaml           # Keep
├─ data/                       # Keep
├─ .github/
│   └─ workflows/
│       ├─ test.yml            # NEW: Run tests on PR
│       └─ docker-build.yml    # NEW: Build/push Docker image
├─ docker-compose.yml          # Update for fastmcp
├─ Dockerfile                  # Update for fastmcp
├─ pyproject.toml              # Update dependencies
└─ README.md                   # Rewrite for fastmcp

REMOVE:
❌ src/learning_mcp/routes/
❌ src/learning_mcp/app.py
❌ src/learning_mcp/jobs_db.py
❌ src/learning_mcp/job_manager.py
❌ src/learning_mcp/autogen_agent.py
❌ src/utils/
❌ state/
❌ CLEANUP_SPEC.md (this file - replace with docs/MIGRATION.md)
```

---

## Implementation Plan

### Phase 1: Core MCP Server (Day 1)

**File**: `src/mcp_server.py`

```python
#!/usr/bin/env python3
"""
Learning MCP Server - Simple RAG over documents

Run: fastmcp run mcp_server.py
Test: pytest tests/test_mcp_tools.py
"""
from fastmcp import FastMCP, Context
from learning_mcp.core.config import settings
from learning_mcp.core.embeddings import EmbeddingConfig, Embedder
from learning_mcp.core.vdb import VDB
from learning_mcp.core.document_loaders import collect_chunks
import logging

log = logging.getLogger(__name__)

# Create MCP server
mcp = FastMCP("Learning MCP - RAG Server")

@mcp.tool
async def search_docs(
    q: str, 
    profile: str, 
    top_k: int = 5,
    ctx: Context = None
) -> dict:
    """
    Search documents with semantic similarity.
    
    Args:
        q: Search query
        profile: Profile name from learning.yaml
        top_k: Number of results (1-20)
        ctx: MCP context (auto-injected)
    
    Returns:
        {"results": [{text, score, metadata}, ...]}
    """
    if ctx:
        await ctx.info(f"Searching '{profile}' for: {q}")
    
    # Load profile
    profiles_cfg = settings.load_profiles()
    prof = next((p for p in profiles_cfg.get("profiles", []) if p.get("name") == profile), None)
    if not prof:
        return {"error": f"Profile '{profile}' not found"}
    
    # Embed query
    ecfg = EmbeddingConfig.from_profile(prof)
    embedder = Embedder(ecfg)
    try:
        qvec = (await embedder.embed([q]))[0]
    finally:
        await embedder.close()
    
    # Search Qdrant
    vcfg = prof.get("vectordb", {})
    vdb = VDB(
        url=vcfg.get("url"),
        collection=vcfg.get("collection"),
        dim=ecfg.dim,
        distance=vcfg.get("distance", "cosine")
    )
    hits = vdb.search(qvec, top_k=min(top_k, 20), filter_by={"doc_id": profile})
    
    # Format results
    results = []
    for pt in hits:
        payload = getattr(pt, "payload", {}) or {}
        results.append({
            "text": payload.get("text", "")[:500],
            "score": float(getattr(pt, "score", 0.0)),
            "metadata": {
                "doc_path": payload.get("doc_path"),
                "chunk_idx": payload.get("chunk_idx")
            }
        })
    
    if ctx:
        await ctx.info(f"Found {len(results)} results")
    
    return {"results": results, "profile": profile, "query": q}


@mcp.tool
async def ingest_profile(
    profile: str, 
    truncate: bool = False,
    ctx: Context = None
) -> dict:
    """
    Ingest documents for a profile (load, chunk, embed, store).
    
    Args:
        profile: Profile name from learning.yaml
        truncate: If true, clear existing collection first
        ctx: MCP context (auto-injected)
    
    Returns:
        {"status": "ok", "chunks_ingested": 123, "time_seconds": 45.2}
    """
    import time
    t0 = time.time()
    
    if ctx:
        await ctx.info(f"Ingesting profile: {profile}")
    
    # Load profile
    profiles_cfg = settings.load_profiles()
    prof = next((p for p in profiles_cfg.get("profiles", []) if p.get("name") == profile), None)
    if not prof:
        return {"error": f"Profile '{profile}' not found"}
    
    # Setup
    ecfg = EmbeddingConfig.from_profile(prof)
    vcfg = prof.get("vectordb", {})
    cparams = prof.get("chunking", {})
    
    vdb = VDB(
        url=vcfg.get("url"),
        collection=vcfg.get("collection"),
        dim=ecfg.dim,
        distance=vcfg.get("distance", "cosine")
    )
    
    if truncate:
        if ctx:
            await ctx.info("Truncating collection...")
        vdb.truncate()
    else:
        vdb.ensure_collection()
    
    # Load chunks
    if ctx:
        await ctx.info("Loading documents...")
    chunks, stats = collect_chunks(
        prof,
        chunk_size=cparams.get("size", 1200),
        chunk_overlap=cparams.get("overlap", 200)
    )
    
    if not chunks:
        return {"error": "No documents found in profile"}
    
    # Embed
    if ctx:
        await ctx.info(f"Embedding {len(chunks)} chunks...")
        await ctx.report_progress(0.0, len(chunks))
    
    embedder = Embedder(ecfg)
    try:
        texts = [c.get("text", "") for c in chunks]
        vecs = await embedder.embed(texts)
        
        # Upsert
        if ctx:
            await ctx.info("Storing vectors...")
        payloads = [
            {
                "doc_id": profile,
                "text": c.get("text", ""),
                "doc_path": (c.get("metadata") or {}).get("doc_path"),
                "chunk_idx": i
            }
            for i, c in enumerate(chunks)
        ]
        vdb.upsert(vectors=vecs, payloads=payloads)
        
        if ctx:
            await ctx.report_progress(len(chunks), len(chunks))
            await ctx.info(f"✓ Ingested {len(chunks)} chunks in {time.time()-t0:.1f}s")
        
        return {
            "status": "ok",
            "profile": profile,
            "chunks_ingested": len(chunks),
            "time_seconds": round(time.time() - t0, 2)
        }
    finally:
        await embedder.close()


@mcp.tool
async def list_profiles() -> dict:
    """
    List all available profiles from learning.yaml.
    
    Returns:
        {"profiles": [{"name": "...", "documents": 3, "collection": "..."}, ...]}
    """
    profiles_cfg = settings.load_profiles()
    profiles = profiles_cfg.get("profiles", [])
    
    result = []
    for p in profiles:
        name = p.get("name", "unknown")
        docs = p.get("documents", [])
        vcfg = p.get("vectordb", {})
        
        result.append({
            "name": name,
            "documents_count": len(docs),
            "collection": vcfg.get("collection", ""),
            "embedding_backend": (p.get("embedding", {}).get("backend", {}).get("primary", "ollama"))
        })
    
    return {"profiles": result, "count": len(result)}


@mcp.resource("profile://{name}")
async def get_profile_config(name: str) -> str:
    """
    Get detailed configuration for a profile.
    
    Args:
        name: Profile name
    
    Returns:
        JSON string with profile configuration
    """
    import json
    profiles_cfg = settings.load_profiles()
    prof = next((p for p in profiles_cfg.get("profiles", []) if p.get("name") == name), None)
    
    if not prof:
        return json.dumps({"error": f"Profile '{name}' not found"})
    
    return json.dumps(prof, indent=2)


if __name__ == "__main__":
    # Run with stdio (default for Claude Desktop)
    mcp.run()
    
    # For HTTP testing, use:
    # mcp.run(transport="http", host="0.0.0.0", port=8013, path="/mcp")
```

### Phase 2: Testing (Day 1-2)

**File**: `tests/test_mcp_tools.py`

```python
"""
Test MCP tools using fastmcp's in-memory client.
"""
import pytest
from fastmcp import Client
from mcp_server import mcp

@pytest.mark.asyncio
async def test_list_profiles():
    """Test listing profiles."""
    async with Client(mcp) as client:
        result = await client.call_tool("list_profiles", {})
        data = result.content[0].text
        
        # Should have dahua-camera, informatica-cloud profiles
        assert "profiles" in data
        assert "dahua-camera" in data or "informatica-cloud" in data


@pytest.mark.asyncio
async def test_search_docs():
    """Test semantic search (requires Qdrant + data)."""
    async with Client(mcp) as client:
        # First check if profile exists
        profiles_result = await client.call_tool("list_profiles", {})
        
        # Search (might fail if not ingested yet)
        result = await client.call_tool("search_docs", {
            "q": "test query",
            "profile": "dahua-camera",
            "top_k": 3
        })
        data = result.content[0].text
        assert "results" in data or "error" in data


@pytest.mark.asyncio
async def test_get_profile_resource():
    """Test profile resource."""
    async with Client(mcp) as client:
        resources = await client.list_resources()
        
        # Should have profile:// template
        assert any("profile://" in r.uri for r in resources)
```

**File**: `tests/test_core/test_embeddings.py`

```python
"""
Test embedding functionality.
"""
import pytest
from learning_mcp.core.embeddings import EmbeddingConfig, Embedder

@pytest.mark.asyncio
async def test_embedder_ollama():
    """Test Ollama embedding (if available)."""
    cfg = EmbeddingConfig(
        dim=768,
        primary="ollama",
        ollama_host="http://localhost:11434",
        ollama_model="nomic-embed-text"
    )
    embedder = Embedder(cfg)
    
    try:
        vecs = await embedder.embed(["hello world"])
        assert len(vecs) == 1
        assert len(vecs[0]) == 768
    except Exception as e:
        pytest.skip(f"Ollama not available: {e}")
    finally:
        await embedder.close()
```

### Phase 3: Docker & Deployment (Day 2)

**File**: `Dockerfile`

```dockerfile
FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl ca-certificates tini git && \
    rm -rf /var/lib/apt/lists/*

# Install uv
RUN curl -LsSf https://astral.sh/uv/install.sh | sh
ENV PATH="/root/.local/bin:${PATH}"
ENV PYTHONPATH="/app/src"

WORKDIR /app

# Copy project files
COPY pyproject.toml ./
COPY src ./src
COPY config ./config
COPY data ./data

# Install dependencies with uv
RUN uv pip install --system fastmcp httpx pyyaml pypdf qdrant-client python-dotenv pydantic-settings

EXPOSE 8013

# Default: stdio mode (for debugging, use HTTP)
ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["fastmcp", "run", "/app/src/mcp_server.py"]
```

**File**: `docker-compose.yml`

```yaml
services:
  vector-db:
    image: qdrant/qdrant:latest
    ports:
      - "6333:6333"
    volumes:
      - qdrant_data:/qdrant/storage
    healthcheck:
      test: ["CMD", "curl", "-fsS", "http://localhost:6333/readyz"]
      interval: 5s
      timeout: 2s
      retries: 20
    restart: unless-stopped
    networks:
      - app-network

  learning-mcp:
    build:
      context: .
      dockerfile: Dockerfile
    env_file:
      - .env
    ports:
      - "8013:8013"
    volumes:
      - ./src:/app/src:rw
      - ./config:/app/config:ro
      - ./data:/app/data:ro
    # For stdio (Claude Desktop): use default CMD
    # For HTTP testing: override with http transport
    command: >
      fastmcp run /app/src/mcp_server.py --transport http --host 0.0.0.0 --port 8013
    depends_on:
      vector-db:
        condition: service_healthy
    restart: unless-stopped
    networks:
      - app-network

volumes:
  qdrant_data:

networks:
  app-network:
    driver: bridge
```

### Phase 4: GitHub Actions (Day 2-3)

**File**: `.github/workflows/test.yml`

```yaml
name: Tests

on:
  push:
    branches: [ main, v2-fastmcp-simplified ]
  pull_request:
    branches: [ main ]

jobs:
  test:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        python-version: ['3.12']
    
    steps:
    - uses: actions/checkout@v4
    
    - name: Set up Python
      uses: actions/setup-python@v5
      with:
        python-version: ${{ matrix.python-version }}
    
    - name: Install uv
      run: curl -LsSf https://astral.sh/uv/install.sh | sh
    
    - name: Install dependencies
      run: |
        uv pip install --system fastmcp httpx pyyaml pypdf qdrant-client python-dotenv pydantic-settings pytest pytest-asyncio pytest-cov
    
    - name: Run tests
      run: |
        export PYTHONPATH="${PYTHONPATH}:${PWD}/src"
        pytest tests/ --cov=src/learning_mcp --cov-report=xml --cov-report=term
    
    - name: Upload coverage
      uses: codecov/codecov-action@v4
      with:
        file: ./coverage.xml
        fail_ci_if_error: false
```

**File**: `.github/workflows/docker-build.yml`

```yaml
name: Docker Build & Push

on:
  push:
    branches: [ main ]
    tags: [ 'v*' ]
  pull_request:
    branches: [ main ]

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
      if: github.event_name != 'pull_request'
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
          type=ref,event=pr
          type=semver,pattern={{version}}
          type=semver,pattern={{major}}.{{minor}}
    
    - name: Build and push
      uses: docker/build-push-action@v5
      with:
        context: .
        push: ${{ github.event_name != 'pull_request' }}
        tags: ${{ steps.meta.outputs.tags }}
        labels: ${{ steps.meta.outputs.labels }}
```

---

## Updated Dependencies

**File**: `pyproject.toml`

```toml
[project]
name = "learning-mcp"
version = "2.0.0"
requires-python = ">=3.12"
dependencies = [
  "fastmcp>=2.13.0",
  "httpx",
  "pyyaml",
  "pypdf",
  "qdrant-client",
  "python-dotenv",
  "pydantic-settings",
]

[project.optional-dependencies]
dev = [
  "pytest>=7.0",
  "pytest-asyncio",
  "pytest-cov",
]

[build-system]
requires = ["setuptools", "wheel"]
build-backend = "setuptools.build_meta"

[tool.setuptools.packages.find]
where = ["src"]
```

---

## Testing Strategy

### Unit Tests (Core Logic)
```powershell
# Test embeddings, VDB, loaders
pytest tests/test_core/ -v

# With coverage
pytest tests/test_core/ --cov=src/learning_mcp/core --cov-report=html
```

### Integration Tests (MCP Tools)
```powershell
# Requires Qdrant running
docker compose up -d vector-db

# Test MCP tools with in-memory client
pytest tests/test_mcp_tools.py -v

# Cleanup
docker compose down
```

### Manual Testing (Claude Desktop)
```json
// ~/.config/claude/claude_desktop_config.json (Linux/macOS)
// %APPDATA%\Claude\claude_desktop_config.json (Windows)
{
  "mcpServers": {
    "learning-mcp": {
      "command": "docker",
      "args": [
        "compose",
        "exec",
        "-T",
        "learning-mcp",
        "fastmcp",
        "run",
        "/app/src/mcp_server.py"
      ]
    }
  }
}
```

### HTTP Testing (Optional)
```powershell
# Start with HTTP transport
docker compose up --build

# Test tools via HTTP (requires MCP-over-HTTP client)
curl http://localhost:8013/mcp
```

---

## Migration Steps

### Step 1: Backup Current Code
```powershell
git checkout -b v2-fastmcp-simplified
git add -A
git commit -m "Backup before fastmcp migration"
```

### Step 2: Install fastmcp
```powershell
uv pip install fastmcp
```

### Step 3: Create New Structure
```powershell
# Create new mcp_server.py
New-Item -Path "src\mcp_server.py" -ItemType File

# Rename learning_mcp to core
Move-Item "src\learning_mcp" "src\learning_mcp_backup"
New-Item -Path "src\learning_mcp\core" -ItemType Directory
Copy-Item "src\learning_mcp_backup\embeddings.py" "src\learning_mcp\core\"
Copy-Item "src\learning_mcp_backup\vdb.py" "src\learning_mcp\core\"
# ... copy other core files

# Create tests
New-Item -Path "tests" -ItemType Directory
New-Item -Path "tests\test_core" -ItemType Directory
```

### Step 4: Implement & Test
```powershell
# Implement mcp_server.py (see Phase 1 code above)
# Write tests (see Phase 2 code above)

# Run tests
pytest tests/ -v
```

### Step 5: Update Docker
```powershell
# Update Dockerfile and docker-compose.yml (see Phase 3)
docker compose build
docker compose up
```

### Step 6: GitHub Actions
```powershell
# Create .github/workflows/ files (see Phase 4)
git add .github/workflows/
git commit -m "Add CI/CD workflows"
git push origin v2-fastmcp-simplified
```

---

## Success Criteria

### ✅ MCP Server Works
- [ ] `fastmcp run mcp_server.py` starts without errors
- [ ] Claude Desktop can connect and see 3 tools
- [ ] `list_profiles` returns profiles from learning.yaml
- [ ] `search_docs` returns semantic results
- [ ] `ingest_profile` loads and embeds documents

### ✅ Tests Pass
- [ ] All unit tests pass (`pytest tests/test_core/`)
- [ ] MCP integration tests pass (`pytest tests/test_mcp_tools.py`)
- [ ] Code coverage > 60%

### ✅ Docker Works
- [ ] `docker compose up --build` succeeds
- [ ] Can ingest via `docker compose exec learning-mcp fastmcp run ...`
- [ ] Qdrant stores vectors correctly

### ✅ CI/CD Works
- [ ] GitHub Actions tests run on PR
- [ ] Docker image builds and pushes to ghcr.io
- [ ] Coverage report uploads to Codecov

---

## GitHub Features to Enable

### 1. Branch Protection
```
Settings → Branches → Add rule for `main`:
  ✅ Require pull request before merging
  ✅ Require status checks (test.yml must pass)
  ✅ Require branches to be up to date
```

### 2. GitHub Packages (Container Registry)
```
Settings → Actions → General:
  ✅ Read and write permissions (for ghcr.io push)
```

### 3. Codecov Integration
```
# Install Codecov GitHub App
https://github.com/apps/codecov

# Add CODECOV_TOKEN to repository secrets (optional)
Settings → Secrets → Actions → New repository secret
```

### 4. Dependabot (Optional)
```yaml
# .github/dependabot.yml
version: 2
updates:
  - package-ecosystem: "pip"
    directory: "/"
    schedule:
      interval: "weekly"
  - package-ecosystem: "docker"
    directory: "/"
    schedule:
      interval: "weekly"
  - package-ecosystem: "github-actions"
    directory: "/"
    schedule:
      interval: "weekly"
```

---

## Timeline & Effort

| Phase | Tasks | Effort | Status |
|-------|-------|--------|--------|
| **Phase 1** | Create `mcp_server.py`, reorganize core | 4 hours | 🔄 Pending |
| **Phase 2** | Write tests (unit + integration) | 3 hours | 🔄 Pending |
| **Phase 3** | Update Docker files, test locally | 2 hours | 🔄 Pending |
| **Phase 4** | GitHub Actions, push to repo | 2 hours | 🔄 Pending |
| **Total** | **Complete V2.0** | **~11 hours** | 🔄 Pending |

---

## Review Questions ✅ ANSWERED

1. **Ingest Timing**: ✅ **On-demand only** - Cleaner, user-controlled via MCP tool
   
2. **HTTP Transport**: ✅ **HTTP Streaming (SSE)** - Required for MCP over HTTP, works with Claude Desktop
   - Will use `mcp.run(transport="sse", host="0.0.0.0", port=8013)`
   - Enables both local (stdio) and remote (HTTP SSE) access
   
3. **AutoGen**: ✅ **Keep for API Planning** - Useful for intelligent API call generation
   - Move to `src/learning_mcp/agents/autogen_planner.py` (separate module)
   - Add 4th MCP tool: `plan_api_call` (uses AutoGen for smart planning)
   - Can be disabled via env var: `USE_AUTOGEN=0`
   
4. **Test Coverage Target**: ✅ **80% for core functionality**
   - embeddings.py, vdb.py, document_loaders.py: 80%+
   - mcp_server.py: 70%+ (some tools require live services)
   - Overall project: 75%+

---

## Next Steps

Once you approve this spec:

1. **I will**:
   - Create new branch `v2-fastmcp-simplified`
   - Implement `mcp_server.py` (Phase 1)
   - Write tests (Phase 2)
   - Update Docker files (Phase 3)
   - Create GitHub Actions (Phase 4)
   - Update README.md
   - Test everything end-to-end

2. **You will**:
   - Review the PR
   - Test with Claude Desktop
   - Merge to main when satisfied

**Ready to proceed?** Answer the 4 review questions above and say "approved" to start! 🚀
