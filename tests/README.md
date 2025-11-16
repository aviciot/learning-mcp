# Test Suite

Comprehensive test suite for Learning MCP v2.0 with 80% coverage target.

## Structure

```
tests/
├── conftest.py              # Shared fixtures and pytest config
├── test_core/               # Unit tests for core modules
│   ├── test_embeddings.py   # Embedder, caching, fallback
│   ├── test_vdb.py          # Qdrant wrapper (VDB)
│   └── test_loaders.py      # PDF/JSON document loaders
├── integration/             # Integration tests (services running)
│   ├── test_search_integration.py    # End-to-end search workflow
│   ├── test_api_planning.py          # AutoGen agent integration
│   └── test_api_planning_simple.py   # Simplified agent tests
├── manual/                  # Manual exploratory tests (not in CI)
│   ├── test_gateway_flow.py          # Gateway architecture explanation
│   ├── test_gateway_proof.py         # Gateway behavior proof
│   ├── test_gateway_real.py          # Real Gateway API calls
│   ├── test_check_gateway_config.py  # Query CF API for gateway config
│   ├── test_gateway_tokens_explained.py  # Token authentication docs
│   ├── test_mcp_search.py            # MCP search function test
│   ├── test_search_http_simple.py    # HTTP MCP protocol test
│   ├── test_search_skills.py         # Search metadata validation
│   └── test_technical_skills.py      # Specific query search test
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

### 1. Unit Tests (`test_core/`)
Fast, isolated tests for core modules (no external dependencies).

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

### 2. Integration Tests (`integration/`)
Full workflow tests requiring running services (Qdrant, Ollama/Cloudflare API).

#### `test_search_integration.py`
- End-to-end semantic search workflow
- Document ingestion → chunking → embedding → vector search
- Profile-specific configurations
- Multi-document retrieval with hints

#### `test_api_planning.py`
- AutoGen agent integration (planner + critic loop)
- Retriever → AutoGen → API plan generation
- YAML-driven system message templates
- Evidence evaluation and iterative refinement

#### `test_api_planning_simple.py`
- Simplified AutoGen tests for basic scenarios
- Direct API planning without complex loops
- Faster feedback for common cases

### 3. Manual Tests (`manual/`)
Exploratory tests for understanding and debugging (not run in CI).

#### Gateway Architecture Tests
- **`test_gateway_flow.py`**: Conceptual explanation of Cloudflare AI Gateway flow
- **`test_gateway_proof.py`**: Side-by-side comparison (direct vs. Gateway calls)
- **`test_gateway_real.py`**: Real API calls through Gateway (with provider keys)
- **`test_check_gateway_config.py`**: Query Cloudflare API to inspect gateway config
- **`test_gateway_tokens_explained.py`**: Authentication token documentation

#### Search/MCP Tests
- **`test_mcp_search.py`**: Direct test of MCP search_docs function
- **`test_search_http_simple.py`**: HTTP MCP protocol test via /mcp endpoint
- **`test_search_skills.py`**: Validate search results after metadata removal
- **`test_technical_skills.py`**: Test specific "technical skills" query

**When to run**: Manual exploration, architectural verification, debugging search/MCP issues

**Usage**:
```powershell
# Run from root directory
docker cp tests/manual/test_gateway_proof.py learning-mcp:/app/
docker compose exec learning-mcp python /app/test_gateway_proof.py

# Or run search tests
docker compose exec learning-mcp python tests/manual/test_search_skills.py
```

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
