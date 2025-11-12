# Test Suite

Comprehensive test suite for Learning MCP v2.0 with 80% coverage target.

## Structure

```
tests/
├── conftest.py              # Shared fixtures and pytest config
├── test_mcp_tools.py        # MCP integration tests (fastmcp Client)
├── test_job_api.py          # FastAPI endpoint tests (TestClient)
├── test_core/               # Unit tests for core modules
│   ├── test_embeddings.py   # Embedder, caching, fallback
│   ├── test_vdb.py          # Qdrant wrapper (VDB)
│   └── test_loaders.py      # PDF/JSON document loaders
└── fixtures/                # Sample test data
    └── sample.json          # Sample JSON document
```

## Running Tests

### In Docker (Recommended)
```powershell
# Run all tests with coverage
docker compose exec learning-mcp pytest

# Run specific test file
docker compose exec learning-mcp pytest tests/test_mcp_tools.py

# Run with verbose output
docker compose exec learning-mcp pytest -v

# Generate HTML coverage report
docker compose exec learning-mcp pytest --cov-report=html
# Open htmlcov/index.html in browser
```

### Local Development
```powershell
# Install test dependencies
uv pip install -e ".[test]"

# Run all tests
pytest

# Run with coverage
pytest --cov=src/learning_mcp --cov-report=term-missing

# Run specific test
pytest tests/test_mcp_tools.py::test_list_profiles -v
```

## Test Categories

### 1. MCP Integration Tests (`test_mcp_tools.py`)
- Uses `fastmcp.Client` in-memory testing (no network)
- Tests all 3 MCP tools: `list_profiles`, `search_docs`, `plan_api_call`
- Tests 1 resource: `profile://{name}`
- Coverage: MCP tool logic, error handling, response structure

### 2. Job API Tests (`test_job_api.py`)
- Uses `fastapi.testclient.TestClient` for HTTP testing
- Tests 5 endpoints: POST /ingest/jobs, GET /jobs, GET /jobs/{id}, POST /ingest/cancel_all, GET /health
- Coverage: Job lifecycle, status tracking, cancellation, validation

### 3. Core Module Tests (`test_core/`)

#### `test_embeddings.py`
- Embedder initialization (Ollama/Cloudflare)
- Single-text and batch embedding
- Cache alignment and short-circuit
- Primary/fallback switching on failure
- Dimension validation
- Concurrency and pacing

#### `test_vdb.py`
- VDB initialization with Qdrant client
- Collection creation (ensure_collection)
- Point upsert with deterministic UUIDv5 IDs
- Search with filters, top_k, score_threshold
- Truncate (delete + recreate)
- Error handling

#### `test_loaders.py`
- Loader registry (`_LOADER_BY_TYPE`)
- PDF loading with page ranges
- JSON loading (nested objects, arrays)
- Metadata preservation
- Invalid file handling
- Type dispatch via `load_document()`

## Coverage Targets

- **Core modules**: 80% (embeddings, vdb, loaders)
- **MCP server**: 70% (mcp_server.py)
- **Job server**: 70% (job_server.py)
- **Overall**: 75%

## Writing New Tests

### Test Fixtures
Use shared fixtures from `conftest.py`:
```python
def test_with_config(test_config):
    # test_config provides sample embedding/vdb config
    assert test_config["embedding"]["dim"] == 768
```

### Async Tests
Use `@pytest.mark.asyncio` for async functions:
```python
@pytest.mark.asyncio
async def test_async_operation():
    result = await some_async_function()
    assert result is not None
```

### Mocking External Services
Mock Qdrant/Ollama/Cloudflare to avoid network calls:
```python
@patch('learning_mcp.vdb.QdrantClient')
def test_vdb_operation(mock_qdrant):
    mock_qdrant.return_value.search.return_value = []
    # ... test logic
```

## CI Integration

Tests run automatically on:
- Pull requests (`.github/workflows/test.yml`)
- Main branch pushes
- Manual workflow dispatch

See `CLEANUP_SPEC_V2.md` for GitHub Actions configuration.

## Troubleshooting

### Import Errors
Ensure `PYTHONPATH` includes `src/`:
```python
import sys
sys.path.insert(0, 'src')
```

### Async Warnings
If you see "no running event loop", add `@pytest.mark.asyncio`.

### Coverage Too Low
1. Check `htmlcov/index.html` for uncovered lines
2. Add tests for missing branches (if/else, try/except)
3. Verify `[tool.coverage.run]` omit patterns in `pyproject.toml`

### Docker Test Failures
```powershell
# Rebuild with test dependencies
docker compose build learning-mcp

# Check logs
docker compose logs learning-mcp

# Run interactively for debugging
docker compose exec learning-mcp bash
pytest -v --pdb  # Drop into debugger on failure
```
