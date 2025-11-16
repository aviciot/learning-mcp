# Test Reorganization Summary

## Completed: November 16, 2025

### New Structure

```
tests/
├── test_core/               # Unit tests (existing)
│   ├── test_embeddings.py
│   ├── test_vdb.py
│   └── test_loaders.py
│
├── integration/             # Integration tests (NEW)
│   ├── test_search_integration.py     ← moved from root
│   ├── test_api_planning.py          ← moved from root
│   └── test_api_planning_simple.py   ← moved from root
│
└── manual/                  # Manual exploratory tests (NEW)
    ├── test_gateway_flow.py          ← moved from root
    ├── test_gateway_proof.py         ← moved from root
    ├── test_gateway_real.py          ← moved from root
    ├── test_check_gateway_config.py  ← moved from root
    └── test_gateway_tokens_explained.py  ← moved from root
```

### Files Moved

**To `tests/integration/`** (require running services):
- ✅ `test_search_integration.py` - End-to-end search workflow
- ✅ `test_api_planning.py` - AutoGen agent integration
- ✅ `test_api_planning_simple.py` - Simplified agent tests

**To `tests/manual/`** (exploratory, not in CI):
- ✅ `test_gateway_flow.py` - Gateway architecture explanation
- ✅ `test_gateway_proof.py` - Gateway behavior proof with real API calls
- ✅ `test_gateway_real.py` - Gateway API call testing
- ✅ `test_check_gateway_config.py` - Query Cloudflare API for gateway config
- ✅ `test_gateway_tokens_explained.py` - Authentication token documentation

### Remaining Root Tests (To Review)

Still in project root (need evaluation):
- `test_mcp_search.py` - MCP search tool test (maybe → integration/)
- `test_search_http_simple.py` - Simple HTTP search test (maybe → integration/)
- `test_search_skills.py` - Search skills test (unclear purpose, review needed)
- `test_technical_skills.py` - Technical skills test (unclear purpose, review needed)

**Action needed**: Review these files and either:
1. Move to `tests/integration/` if they test workflows
2. Move to `tests/manual/` if they're exploratory
3. Delete if obsolete/redundant

### Running Tests

#### Unit Tests (fast, no external dependencies)
```powershell
docker compose exec learning-mcp pytest tests/test_core/ -v
```

#### Integration Tests (require services)
```powershell
# Ensure services are running
docker compose exec learning-mcp pytest tests/integration/ -v
```

#### Manual Tests (exploratory)
```powershell
# Copy to container and run directly
docker cp tests/manual/test_gateway_proof.py learning-mcp:/app/
docker compose exec learning-mcp python /app/test_gateway_proof.py
```

### Benefits

1. **Clear separation**: Unit vs. integration vs. exploratory tests
2. **Faster CI**: Can run unit tests without services, integration tests in separate stage
3. **Better documentation**: README explains each category's purpose
4. **Easier navigation**: Tests organized by purpose, not chronology
5. **Manual tests preserved**: Gateway exploration tests kept for future reference

### CI Impact

**Current**: All tests run together (slow, fragile)

**Proposed** (future):
```yaml
jobs:
  unit-tests:
    runs-on: ubuntu-latest
    steps:
      - pytest tests/test_core/ --cov

  integration-tests:
    runs-on: ubuntu-latest
    services:
      qdrant:
        image: qdrant/qdrant
    steps:
      - pytest tests/integration/ --cov
```

### Next Steps

1. ✅ **DONE**: Create `tests/integration/` and `tests/manual/` directories
2. ✅ **DONE**: Move integration tests to new location
3. ✅ **DONE**: Move manual Gateway tests to new location
4. ✅ **DONE**: Update `tests/README.md` with new structure
5. ⏳ **TODO**: Review remaining root tests (`test_mcp_search.py`, etc.)
6. ⏳ **TODO**: Update CI workflow to run tests separately by category
7. ⏳ **TODO**: Add `pytest.ini` markers for test categories

---

**Verified**: Test structure reorganized successfully  
**Updated**: `tests/README.md` with new layout and usage instructions  
**Status**: Awaiting review of remaining 4 root-level tests
