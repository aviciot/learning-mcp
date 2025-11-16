# Learning MCP

Learning MCP is a FastAPI-based RAG (Retrieval-Augmented Generation) system with Model Context Protocol (MCP) integration. It provides semantic search over PDF/JSON documentation and AutoGen-powered API planning capabilities.

## 🎯 Key Features

- **Semantic Search**: Vector-based document search using Qdrant and embeddings (Cloudflare/Ollama)
- **MCP Integration**: FastMCP tools for AI agent interactions (`search_docs`, `plan_api_call`)
- **AutoGen Multi-Agent**: Planner + Critic agents for generating accurate API calls from documentation
- **Profile System**: Per-profile configurations for different API documentation sets
- **Background Ingestion**: Async job system for document processing with progress tracking
- **AI Gateway**: Cloudflare AI Gateway integration for caching, rate limiting, and analytics

## 📖 Documentation

**→ [Complete Documentation](docs/README.md)** - Comprehensive guides, architecture, and API reference

### Quick Links

- **[AutoGen Multi-Agent Planner](docs/architecture/autogen-multi-agent-planner.md)** - How AI agents generate API plans
- **[Cloudflare AI Gateway](docs/architecture/cloudflare-ai-gateway.md)** - Gateway setup and configuration
- **[Search & RAG Features](docs/architecture/search-and-rag-features.md)** - Vector search architecture
- **[MCP Testing Guide](docs/development/mcp-testing-guide.md)** - Testing strategies and examples

## 🚀 Quick Start

## 🚀 Quick Start

### Prerequisites

- Docker with Docker Compose
- Qdrant instance (included in docker-compose)
- Cloudflare API token (for embeddings) OR Ollama instance
- (Optional) Groq API key for AutoGen features

### 1. Clone and Configure

```bash
git clone https://github.com/aviciot/learning-mcp.git
cd learning-mcp

# Create .env file
cp .env.example .env
# Edit .env with your credentials
```

### 2. Start Services

```bash
docker compose up --build
```

Services will be available at:
- **MCP Server**: http://localhost:8013/mcp (FastMCP HTTP transport)
- **Job Server**: http://localhost:8014 (ingestion status)
- **Swagger UI**: http://localhost:8013/docs

### 3. Ingest Documentation

```bash
# Start ingestion job
curl -X POST http://localhost:8014/ingest/jobs \
  -H "Content-Type: application/json" \
  -d '{"profile": "dahua-camera", "truncate": true}'

# Check status
curl http://localhost:8014/jobs
```

### 4. Test MCP Tools

Using MCPJam, Claude Desktop, or any MCP client:

```python
# search_docs tool
{
  "q": "how to configure wifi",
  "profile": "dahua-camera",
  "top_k": 5
}

# plan_api_call tool (requires AutoGen)
{
  "goal": "get job status",
  "profile": "informatica-cloud"
}
```

## ⚙️ Configuration

## ⚙️ Configuration

### Environment Variables

Key variables in `.env`:

```bash
# === Embedding ===
CF_ACCOUNT_ID=your_account_id
CF_API_TOKEN=your_api_token
CF_MODEL=@cf/baai/bge-small-en-v1.5
OLLAMA_HOST=http://host.docker.internal:11434
EMBED_MODEL=nomic-embed-text

# === Vector DB ===
VECTOR_DB_URL=http://vector-db:6333

# === AutoGen (Optional) ===
USE_AUTOGEN=1
AUTOGEN_BACKEND=groq
GROQ_API_KEY=gsk_...
OPENAI_BASE_URL=https://gateway.ai.cloudflare.com/v1/{account}/omni/compat
CF_GATEWAY_TOKEN=your_gateway_token

# === Servers ===
PORT=8013
LOG_LEVEL=info
```

### Profile System

Profiles defined in `config/learning.yaml`:

```yaml
dahua-camera:
  documents:
    - type: pdf
      path: /app/data/dahua/HTTP_API.pdf
  
  chunking:
    max_tokens: 1200
    overlap: 200
  
  embedding:
    dim: 384
    backend:
      primary: cloudflare
      fallback: ollama
  
  vectordb:
    collection: dahua-camera
    distance: Cosine
  
  autogen_hints:  # For plan_api_call tool
    endpoint:
      allow: "^/cgi-bin/.*"
    templates:
      write:
        require_example_in_evidence: true
```

See **[docs/README.md](docs/README.md)** for complete configuration guide.

## 🏗️ Architecture

```
┌─────────────────────────────────────────┐
│  MCP Server (FastMCP - Port 8013)       │
│  Tools: search_docs, plan_api_call      │
└─────────────────────────────────────────┘
                   │
        ┌──────────┼──────────┐
        │          │          │
        ▼          ▼          ▼
   ┌─────────┐ ┌──────┐ ┌─────────┐
   │ Qdrant  │ │ Embed│ │ AutoGen │
   │ Vector  │ │ (CF/ │ │ Planner │
   │   DB    │ │Ollama│ │ +Critic │
   └─────────┘ └──────┘ └─────────┘
                   │
                   ▼
        ┌──────────────────────┐
        │ Job Server (Port 8014│
        │ Background Ingestion │
        └──────────────────────┘
```

## 📡 API Reference
### MCP Tools (Port 8013 - /mcp)

| Tool | Purpose | Key Parameters |
|------|---------|----------------|
| `search_docs` | Vector similarity search over ingested documents | `query`, `profile`, `top_k` |
| `plan_api_call` | AutoGen-powered API planning with evidence retrieval | `query`, `profile`, `autogen_model` |

**Swagger UI**: `http://localhost:8013/docs`

### Job Server (Port 8014)

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/ingest/jobs` | POST | Enqueue document ingestion (background) |
| `/jobs` | GET | List all jobs |
| `/jobs/{job_id}` | GET | Get job details |
| `/ingest/cancel_all` | POST | Cancel all running ingest jobs |

See **[docs/README.md](docs/README.md)** for complete API reference with examples.

##  Testing

``powershell
# Test MCP tools via HTTP
curl http://localhost:8013/mcp

# Search test
curl -X POST http://localhost:8013/search/api_context -H "Content-Type: application/json" -d '{\"q\":\"wifi settings\",\"profile\":\"dahua-camera\"}'

# AutoGen planner test
curl -X POST http://localhost:8013/agent/api -H "Content-Type: application/json" -d '{\"q\":\"enable audio\",\"profile\":\"dahua-camera\"}'
``

See **[docs/development/mcp-testing-guide.md](docs/development/mcp-testing-guide.md)** for comprehensive testing strategies.

##  Development

``
src/
 learning_mcp/
    app.py              # FastAPI entrypoint + MCP integration
    embeddings.py       # Ollama/Cloudflare embedding with fallback
    vdb.py              # Qdrant vector DB wrapper
    autogen_agent.py    # Multi-agent planner (planner + critic)
    routes/             # API endpoints by concern
 tools/                  # CLI utilities
``

**Adding a new document type:**
1. Implement loader in `src/learning_mcp/<type>_loader.py` returning `List[Chunk]`
2. Register in `document_loaders._LOADER_BY_TYPE`
3. Add to profile YAML: `documents: [{type: <type>, path: ...}]`

**Adding a new MCP tool:**
1. Create route in `routes/` with `@mcp.tool()` decorator
2. Include in `mcp.include_operations` in `app.py`

See **[Architecture Docs](docs/architecture/)** for detailed system design.

##  Troubleshooting

| Issue | Solution |
|-------|----------|
| Embedding dimension mismatch | Check `profile.embedding.dim` matches model output (test with `/debug/embed`) |
| Qdrant connection fails | Verify `VECTOR_DB_URL=http://qdrant:6333` in `.env` and Qdrant container running |
| AutoGen not working | Set `USE_AUTOGEN=true` and install: `pip install pyautogen` |
| Ollama timeout | Increase `keep_alive` in profile or switch to Cloudflare backend |
| Job stuck | Cancel with `POST /ingest/cancel_all`, check logs for errors |

See **[docs/README.md#troubleshooting](docs/README.md#troubleshooting)** for complete guide.

##  Resources

- **[Documentation Hub](docs/README.md)** - Complete guides and architecture docs
- **[AutoGen Multi-Agent Planner](docs/architecture/autogen-multi-agent-planner.md)** - How the planner + critic loop works
- **[Search & RAG Features](docs/architecture/search-and-rag-features.md)** - Vector search internals
- **[MCP Testing Guide](docs/development/mcp-testing-guide.md)** - Testing strategies

##  License

MIT License - See [LICENSE](LICENSE) for details

##  Contributing

1. Fork the repository
2. Create feature branch: `git checkout -b feature/your-feature`
3. Follow existing code patterns (see `copilot-instructions.md`)
4. Test with Docker Compose: `docker compose up --build`
5. Submit PR with clear description

##  Links

- **Repository**: https://github.com/yourusername/learning-mcp
- **Issues**: https://github.com/yourusername/learning-mcp/issues
- **FastMCP**: https://github.com/jlowin/fastmcp
- **AutoGen**: https://microsoft.github.io/autogen/
