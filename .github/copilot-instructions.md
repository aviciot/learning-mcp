# Learning MCP - AI Coding Agent Instructions

## Project Overview

FastAPI service implementing RAG (Retrieval-Augmented Generation) over PDF/JSON documents using Qdrant vector database. The system exposes semantic search and AutoGen-powered API planning endpoints, designed for Model Context Protocol (MCP) workflows.

**Core Flow**: Ingest PDFs/JSON → Chunk → Embed (Ollama/Cloudflare) → Store in Qdrant → Semantic search → AutoGen planner synthesizes API calls

## Architecture

### Major Components
- **`app.py`**: FastAPI entrypoint with MCP integration via `fastapi-mcp` (HTTP transport at `/mcp`)
- **`config.py` + `config/learning.yaml`**: Profile-driven configuration (per-profile embedding, chunking, VDB, AutoGen hints)
- **`embeddings.py`**: Primary/fallback embedding backends (Ollama or Cloudflare Workers AI) with concurrent per-text embedding, retry logic, and optional caching
- **`vdb.py`**: Qdrant wrapper with deterministic UUIDv5 point IDs for idempotent upserts
- **`document_loaders.py`**: Type-agnostic loader registry (PDF via `pdf_loader`, JSON via `json_loader`)
- **`autogen_agent.py`**: AutoGen planner + critic loop (YAML-driven system messages, iterative search/plan/critique)
- **`routes/`**: API endpoints organized by concern (health, ingest, search, API agent)

### Data Flow
1. **Ingest** (`POST /ingest/jobs`): Background asyncio task → load docs → chunk → embed (concurrent, cached) → upsert to Qdrant with UUIDv5 IDs
2. **Search** (`POST /search/api_context`): Query → embed → Qdrant KNN → return scored snippets + hints (URL candidates, method hints, query params)
3. **Agent** (`POST /agent/api`): TTL cache → retriever → AutoGen fallback (planner + critic loop with profile-specific templates)

## Critical Conventions

### Profile System (`config/learning.yaml`)
- **Profiles are the unit of configuration**: Each profile defines documents, chunking strategy, embedding provider (primary/fallback), VDB collection, and optional `autogen_hints`
- **AutoGen hints** in YAML drive planner/critic system messages: `labels`, `endpoint` (allow/forbid patterns), `templates` (read/write forms), `endpoint_examples`
- **Embedding backend precedence**: `profile.embedding.backend.primary` → `profile.embedding.backend.fallback` → env vars (`OLLAMA_HOST`, `CF_ACCOUNT_ID`, etc.)

### Embedding Strategy
- **Concurrency model**: Each text embeds concurrently (controlled by `EMBED_CONCURRENCY`, default 2), not batch-based
- **Pacing**: `EMBED_PACING_MS` (default 150ms) applies to BOTH Ollama and Cloudflare to avoid rate limits
- **Cache alignment**: Pass `ids` (aligned with `texts`) and a `cache` dict to `Embedder.embed()` for short-circuit hits
- **Dimension validation**: Strict match between `profile.embedding.dim` and actual vector length (raises `EmbeddingError` on mismatch)

### Vector DB (Qdrant)
- **Deterministic IDs**: UUIDv5 from `f"{doc_id}|{doc_path}|{chunk_idx}"` for idempotent re-ingests (see `routes/ingest.py` upsert logic)
- **Filtering**: Use `doc_id` (canonical) or `profile` (legacy fallback) in payload filters for multi-tenancy
- **No auto-recreation**: `vdb.ensure_collection()` creates if missing but NEVER recreates on exists (avoid accidental data loss)

### AutoGen Integration
- **Lazy imports**: AutoGen libs imported in `try/except` so server boots even if not installed
- **Two-pass JSON validation**: Planner generates JSON → if invalid, repair pass with explicit instructions
- **Critic feedback loop**: Up to `MAX_LOOPS` (default 3) iterations of search → plan → critique → next_search
- **YAML-driven templates**: `autogen_hints.templates.read` and `templates.write` define expected method/params patterns
- **Acceptance logic**: Read operations accepted if endpoint matches allow pattern + has feature name; writes require concrete example in evidence (when `require_example_in_evidence=true`)

## Development Workflows

### Docker Compose (Primary Development Flow)
```powershell
# Start services (Qdrant + learning-mcp with live reload)
docker compose up --build

# Run Python scripts inside container (loads .env automatically)
docker compose exec learning-mcp python /app/src/tools/<script>.py

# View logs (filtered to app only)
docker compose logs -f learning-mcp

# Restart after config changes
docker compose restart learning-mcp
```

### Environment Setup
- **`.env` file** (not committed): `PORT`, `ENV`, `VECTOR_DB_URL`, `OLLAMA_HOST`, `CF_ACCOUNT_ID`, `CF_API_TOKEN`, `EMBED_MODEL`, `USE_AUTOGEN`, `AUTOGEN_BACKEND`, `AUTOGEN_MODEL`
- **Profile override**: Environment vars override `learning.yaml` fields at runtime (e.g., `VECTOR_DB_URL` beats `profile.vectordb.url`)

### Testing & Debugging
- **Swagger UI**: `http://localhost:8013/docs` (auto-generated; profile dropdowns patched via `custom_openapi()` in `app.py`)
- **MCP Inspector**: Connect to `http://localhost:8013/mcp` (HTTP transport) or use SSE endpoint
- **Health checks**: `GET /health` (service + profile summary), `GET /config/profile/{name}` (profile diagnostics)
- **Embedding test**: `GET /debug/embed` returns vector length for a sample text
- **Job monitoring**: `GET /jobs` (list all ingest jobs), `GET /jobs/{job_id}` (detailed status with SQLite-backed progress tracking)

### Common Commands
```powershell
# Cancel all running ingests (gracefully cancels asyncio tasks)
curl -X POST http://localhost:8013/ingest/cancel_all

# Enqueue ingest with collection truncate
curl -X POST http://localhost:8013/ingest/jobs -H "Content-Type: application/json" -d '{"profile":"dahua-camera","truncate":true}'

# Search with API context hints
curl -X POST http://localhost:8013/search/api_context -H "Content-Type: application/json" -d '{"q":"wifi settings","profile":"dahua-camera","top_k":5}'

# Agent query (cache → retriever → AutoGen)
curl -X POST http://localhost:8013/agent/api -H "Content-Type: application/json" -d '{"q":"how to enable audio","profile":"dahua-camera"}'
```

## Code Patterns

### Adding a New Endpoint
1. Create route module in `src/learning_mcp/routes/` with `router = APIRouter()`
2. Add Pydantic request/response models with `Field(..., description="...")` for Swagger docs
3. Include `operation_id` and `tags` for MCP discoverability
4. Register router in `app.py`: `app.include_router(your_router, prefix="", tags=["your_tag"])`
5. Update `mcp.include_operations` in `app.py` if exposing via MCP

### Adding a Document Type
1. Implement loader function in a new module (e.g., `src/learning_mcp/csv_loader.py`)
2. Return `List[Chunk]` where `Chunk = {"text": str, "metadata": {...}}`
3. Register in `document_loaders._LOADER_BY_TYPE` dict (key = lowercase type string)
4. Add type to profile YAML: `documents: [{type: csv, path: /app/data/example.csv}]`
5. No changes needed in ingest worker (type-agnostic)

### Modifying AutoGen Behavior
- **System messages**: Edit `_build_system_messages_from_hints()` in `autogen_agent.py` to adjust planner/critic templates
- **Acceptance criteria**: Modify `plan_with_autogen()` acceptance logic (search for "# 5) Acceptance" comment)
- **Per-profile customization**: Add fields to `autogen_hints` in profile YAML (e.g., new `templates` or `endpoint` rules)

### Logging Standards
- Use module-level logger: `log = logging.getLogger("learning_mcp.your_module")`
- Structured logs for key events: `log.info(json.dumps({"event": "start", "request_id": rid, ...}))`
- Critical paths (embed, search, AutoGen): Log start/done with timing (`ms=%.1f`)
- Job lifecycle: `job.start`, `job.embed.start`, `job.upsert.ok`, `job.done` with job_id

## Important Gotchas

1. **Windows PowerShell paths**: Always use forward slashes in Docker volume mounts (`./data:/app/data`)
2. **Ollama single-text schema**: Use `{"model": ..., "prompt": text, "keep_alive": ...}` (NOT `input` array)
3. **Qdrant ID constraints**: Must be valid UUID or string (no raw integers); use UUIDv5 for determinism
4. **AutoGen lazy imports**: Wrap imports in `try/except` and check `if AssistantAgent is None` before use
5. **Profile dropdown in Swagger**: `custom_openapi()` patches schema post-generation (runtime only, not MCP Inspector)
6. **Live reload**: Only `/app/src` is mounted read-write in Docker; config/data are read-only
7. **Embedding dimension mismatch**: Server won't start if `profile.embedding.dim` doesn't match model output (validate with `/debug/embed` first)

## MCP-Specific Notes

- **HTTP transport**: Mounted at `/mcp` (recommended over SSE for Claude Desktop)
- **Operation filtering**: Only include stable, well-documented endpoints in `include_operations` (avoid exposing debug routes)
- **Response format**: MCP clients expect JSON; ensure all responses are JSON-serializable (no raw bytes/datetime)
- **Read-only emphasis**: Mark write operations clearly in descriptions; default to `read_only: true` in search endpoints

## Reference Files

- **Entrypoint**: `src/learning_mcp/app.py` (FastAPI setup + router registration)
- **Config**: `config/learning.yaml` (profiles), `src/learning_mcp/config.py` (settings loader)
- **Core logic**: `embeddings.py` (embedding), `vdb.py` (Qdrant), `autogen_agent.py` (planner)
- **Ingest**: `routes/ingest.py` (job enqueue), `document_loaders.py` (type registry)
- **Search**: `routes/search_api.py` (api_context with hints), `routes/api_agent.py` (cache + retriever + AutoGen)
- **Developer guide**: `gprompt` (session-specific conventions for this project)

---

**When in doubt**: Check `gprompt` for PowerShell commands, consult `learning.yaml` for profile structure, or search `routes/` for endpoint patterns.
