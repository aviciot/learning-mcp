# Learning MCP - Documentation

## Overview

Learning MCP is a FastAPI-based RAG (Retrieval-Augmented Generation) system with MCP (Model Context Protocol) integration. It provides semantic search over PDF/JSON documentation and AutoGen-powered API planning capabilities.

## 📚 Documentation Structure

### User Guides

- **[Main README](../README.md)** - Project overview, quickstart, and basic usage
- **[Search & RAG Features](architecture/search-and-rag-features.md)** - Semantic search, vector embeddings, and retrieval capabilities

### Architecture

- **[AutoGen Multi-Agent Planner](architecture/autogen-multi-agent-planner.md)** - How the `plan_api_call` tool uses Planner + Critic agents for API planning
- **[Cloudflare AI Gateway](architecture/cloudflare-ai-gateway.md)** - Gateway configuration, BYOK setup, and Dynamic Routing
- **[Search & RAG Features](architecture/search-and-rag-features.md)** - Vector search architecture, chunking strategies, embedding backends

### Development

- **[MCP Testing Guide](development/mcp-testing-guide.md)** - FastMCP in-memory testing, HTTP testing, and test organization
- **[Tests README](../tests/README.md)** - Test structure, running tests, and coverage

## 🚀 Quick Links

### Getting Started
1. Read the [Main README](../README.md) for setup instructions
2. Configure your `.env` file (see [Main README](../README.md#environment-variables))
3. Run with Docker: `docker compose up --build`

### Key Features
- **Semantic Search**: Vector-based document search with Qdrant
- **Multi-Agent Planning**: AutoGen Planner + Critic for API call generation
- **Profile System**: Per-profile configurations for different API documentation sets
- **MCP Integration**: Tools exposed via Model Context Protocol for AI agents

### API Endpoints

**MCP Server (Port 8013)**
- `POST /mcp` - MCP HTTP transport endpoint
- MCP Tools:
  - `search_docs` - Semantic search over documentation
  - `list_profiles` - Available documentation profiles
  - `plan_api_call` - Generate API calls from natural language (AutoGen)

**Job Server (Port 8014)**
- `POST /ingest/jobs` - Start document ingestion job
- `GET /jobs` - List all ingestion jobs
- `GET /jobs/{job_id}` - Get job status

## 🏗️ Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│  MCP Tools (FastMCP on port 8013)                           │
│  - search_docs                                               │
│  - list_profiles                                             │
│  - plan_api_call                                             │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│  Core Services                                               │
│  ┌──────────────┐  ┌───────────────┐  ┌──────────────┐     │
│  │  Embeddings  │  │  Vector DB    │  │  AutoGen     │     │
│  │  (CF/Ollama) │  │  (Qdrant)     │  │  Agents      │     │
│  └──────────────┘  └───────────────┘  └──────────────┘     │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│  Job Server (FastAPI on port 8014)                          │
│  - Background ingestion                                      │
│  - Job status tracking                                       │
│  - SQLite job database                                       │
└─────────────────────────────────────────────────────────────┘
```

## 🔧 Configuration

### Profile System
Profiles are defined in `config/learning.yaml`:

```yaml
profile-name:
  documents:
    - type: pdf
      path: /app/data/docs.pdf
  
  chunking:
    max_tokens: 1200
    overlap: 200
  
  embedding:
    dim: 384
    backend:
      primary: cloudflare
      fallback: ollama
  
  vectordb:
    collection: profile-name
    distance: Cosine
  
  autogen_hints:
    endpoint:
      allow: ".*"
      forbid: []
    templates:
      read:
        method: GET
      write:
        method: POST
        require_example_in_evidence: true
```

### Environment Variables

Key variables (see `.env`):

```bash
# Embedding
CF_ACCOUNT_ID=...
CF_API_TOKEN=...
OLLAMA_HOST=http://host.docker.internal:11434

# Vector DB
VECTOR_DB_URL=http://vector-db:6333

# AutoGen (optional)
USE_AUTOGEN=1
AUTOGEN_BACKEND=groq
GROQ_API_KEY=gsk_...
OPENAI_BASE_URL=https://gateway.ai.cloudflare.com/v1/.../compat
CF_GATEWAY_TOKEN=...
```

## 📖 Common Workflows

### 1. Ingest Documentation

```bash
# Via API
curl -X POST http://localhost:8014/ingest/jobs \
  -H "Content-Type: application/json" \
  -d '{"profile": "my-profile", "truncate": true}'

# Check status
curl http://localhost:8014/jobs/{job_id}
```

### 2. Search Documentation (via MCP)

```python
# Using FastMCP client
from fastmcp import Client
import asyncio

async def search():
    async with Client("http://localhost:8013/mcp") as client:
        result = await client.call_tool(
            "search_docs",
            arguments={
                "q": "how to configure wifi",
                "profile": "dahua-camera",
                "top_k": 5
            }
        )
        print(result)

asyncio.run(search())
```

### 3. Generate API Plans (via AutoGen)

```python
# Using MCP tool
async with Client("http://localhost:8013/mcp") as client:
    result = await client.call_tool(
        "plan_api_call",
        arguments={
            "goal": "get job status",
            "profile": "informatica-cloud"
        }
    )
    # Returns: {"status": "ok", "plan": {...}, "confidence": 0.9}
```

## 🧪 Testing

```bash
# Run all tests
docker compose exec learning-mcp pytest

# Run with coverage
docker compose exec learning-mcp pytest --cov=src

# Run integration tests only
docker compose exec learning-mcp pytest tests/integration/

# Run specific test
docker compose exec learning-mcp pytest tests/integration/test_mcp_client_e2e.py -v
```

See [MCP Testing Guide](development/mcp-testing-guide.md) for details.

## 📝 Development Guidelines

### Adding a New Profile

1. Add profile to `config/learning.yaml`
2. Place documents in `data/your-profile/`
3. Run ingestion: `POST /ingest/jobs`
4. Test search: Use `search_docs` MCP tool

### Adding a New Document Type

1. Create loader in `src/learning_mcp/{type}_loader.py`
2. Return `List[Chunk]` where `Chunk = {"text": str, "metadata": dict}`
3. Register in `document_loaders._LOADER_BY_TYPE`
4. Add to profile YAML: `documents: [{type: your_type, path: ...}]`

### Modifying AutoGen Behavior

1. Edit system messages in `autogen_planner.py`
2. Adjust profile `autogen_hints` in YAML
3. Test with different confidence thresholds
4. Monitor logs: `docker compose logs -f learning-mcp`

## 🐛 Troubleshooting

### MCP Connection Issues
- Check port 8013 is accessible
- Verify `/mcp` endpoint responds: `curl http://localhost:8013/mcp`
- Check Docker logs: `docker compose logs learning-mcp`

### Embedding Failures
- Test with `/debug/embed` endpoint
- Check `OLLAMA_HOST` or `CF_API_TOKEN` is correct
- Verify dimension matches: `profile.embedding.dim` == model output

### Low Search Quality
- Check if documents are ingested: `GET /config/profile/{name}`
- Verify chunk size appropriate for content
- Try different embedding models
- Increase `top_k` for more results

### AutoGen Returns needs_input
- Check suggested_queries in response
- Run those queries with `search_docs` manually
- Verify documentation has concrete examples
- Adjust `require_example_in_evidence` in profile

## 📚 Additional Resources

- **FastMCP Documentation**: https://gofastmcp.com/
- **AutoGen Documentation**: https://microsoft.github.io/autogen/
- **Qdrant Documentation**: https://qdrant.tech/documentation/
- **Model Context Protocol**: https://modelcontextprotocol.io/

## 🤝 Contributing

See [Main README](../README.md#contributing) for contribution guidelines.

## 📄 License

See [Main README](../README.md#license) for license information.
