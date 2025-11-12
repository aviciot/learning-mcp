# Learning MCP v2.0

**Hybrid Architecture**: MCP Tools + Background Job Management

FastAPI service implementing RAG (Retrieval-Augmented Generation) over PDF/JSON documents using Qdrant vector database. Exposes semantic search and AutoGen-powered API planning via **Model Context Protocol (MCP)** tools, with FastAPI handling background ingestion jobs.

[![Tests](https://github.com/aviciot/learning-mcp/actions/workflows/test.yml/badge.svg)](https://github.com/aviciot/learning-mcp/actions/workflows/test.yml)
[![Coverage](https://img.shields.io/badge/coverage-23.66%25-yellow)](htmlcov/index.html)
[![Docker](https://github.com/aviciot/learning-mcp/actions/workflows/docker-build.yml/badge.svg)](https://github.com/aviciot/learning-mcp/actions/workflows/docker-build.yml)

## 🚀 What's New in v2.0

- **Dual-Server Architecture**: MCP server (port 8013) + Job server (port 8014) running via supervisor
- **fastmcp Integration**: Replaced fastapi-mcp with modern `fastmcp>=0.2.0` using HTTP Streamable transport
- **On-Demand Ingestion**: Start ingest jobs via API, monitor progress, cancel running jobs
- **Comprehensive Testing**: 57 tests (12 passing unit tests, 19 integration tests), 23.66% coverage baseline
- **GitHub Actions CI/CD**: Automated testing on PRs, Docker image publishing to GHCR
- **Refactored Structure**: AutoGen agent moved to `src/learning_mcp/agents/`, cleaner imports

## 🏗️ Architecture

### MCP Server (`mcp_server.py`)
**Purpose**: AI agent interactions via Model Context Protocol  
**Port**: 8013  
**Transport**: HTTP Streamable (`http://localhost:8013/mcp`)  

**Tools**:
- `search_docs`: Semantic search over ingested documents
- `list_profiles`: Get available document profiles
- `plan_api_call`: AutoGen-powered API call planning (optional, requires `USE_AUTOGEN=1`)

**Resources**:
- `profile://{name}`: Read YAML configuration for a specific profile

### Job Server (`job_server.py`)
**Purpose**: Background job management for document ingestion  
**Port**: 8014  
**API Docs**: `http://localhost:8014/docs`

**Endpoints**:
- `POST /ingest/jobs`: Start new ingest job
- `GET /jobs`: List all jobs
- `GET /jobs/{job_id}`: Get job status
- `POST /ingest/cancel_all`: Cancel running jobs
- `GET /health`: Health check

## 📦 Requirements

- **Python**: 3.12+
- **Docker**: With Compose V2
- **Qdrant**: Vector database (included in docker-compose)
- **Embedding Provider**: Ollama (default) or Cloudflare Workers AI
- **Optional**: AutoGen for API planning (`USE_AUTOGEN=1`)

## 🛠️ Quick Start

### 1. Clone and Setup
```powershell
git clone https://github.com/aviciot/learning-mcp.git
cd learning-mcp

# Create .env file (see .env.example)
@"
PORT=8013
JOB_PORT=8014
ENV=dev
VECTOR_DB_URL=http://vector-db:6333
OLLAMA_HOST=http://host.docker.internal:11434
EMBED_MODEL=nomic-embed-text
USE_AUTOGEN=0
"@ | Out-File -Encoding UTF8 .env
```

### 2. Start Services
```powershell
docker compose up --build -d

# Check logs
docker compose logs -f learning-mcp

# Verify health
curl http://localhost:8014/health
```

### 3. Ingest Documents
```powershell
# Start ingest job
curl -X POST http://localhost:8014/ingest/jobs `
  -H "Content-Type: application/json" `
  -d '{"profile":"avi-cohen","truncate":false}'

# Monitor progress
curl http://localhost:8014/jobs
```

### 4. Search Documents (via MCP)
Use MCP Inspector or Claude Desktop to connect to `http://localhost:8013/mcp` and call the `search_docs` tool.

## 🧪 Testing

### Run Tests in Docker
```powershell
# All tests (unit + integration)
docker compose exec learning-mcp python -m pytest tests/ -v

# Unit tests only
docker compose exec learning-mcp python -m pytest tests/test_core/ -v

# With coverage
docker compose exec learning-mcp python -m pytest tests/ --cov=src/learning_mcp --cov-report=html
# Open htmlcov/index.html
```

### Test Coverage by Module
| Module | Coverage | Status |
|--------|----------|--------|
| `embeddings.py` | 51.7% | 🟡 Improving |
| `json_loader.py` | 69.4% | 🟢 Good |
| `pdf_loader.py` | 68.5% | 🟢 Good |
| `document_loaders.py` | 59.0% | 🟡 Acceptable |
| `config.py` | 43.8% | 🟡 Acceptable |
| `vdb.py` | 35.2% | 🔴 Needs work |
| **Overall** | **23.66%** | 🟡 Baseline |

**Target**: 75-80% coverage for core modules by v2.1

## 📁 Project Structure

```
learning-mcp/
├── src/
│   ├── mcp_server.py           # MCP tools (search, list, plan)
│   ├── job_server.py            # FastAPI job management
│   └── learning_mcp/
│       ├── agents/
│       │   └── autogen_planner.py  # AutoGen API planning
│       ├── routes/              # FastAPI routes (legacy)
│       ├── embeddings.py        # Ollama/Cloudflare embedding
│       ├── vdb.py               # Qdrant wrapper
│       ├── document_loaders.py  # PDF/JSON ingestion
│       ├── json_loader.py       # JSON document loader
│       ├── pdf_loader.py        # PDF document loader
│       ├── jobs_db.py           # SQLite job tracking
│       └── config.py            # YAML configuration
├── tests/
│   ├── test_mcp_tools.py        # MCP integration tests (skipped)
│   ├── test_job_api.py          # Job API tests (skipped)
│   └── test_core/               # Unit tests
│       ├── test_embeddings.py   # 13 tests (3 passing)
│       ├── test_vdb.py          # 16 tests (6 passing)
│       └── test_loaders.py      # 13 tests (4 passing)
├── config/
│   └── learning.yaml            # Profiles (avi-cohen, dahua-camera, etc.)
├── data/                        # Mounted documents
├── docker/
│   └── supervisord.conf         # Dual-server process manager
├── .github/
│   └── workflows/
│       ├── test.yml             # CI: Run tests on PR
│       └── docker-build.yml     # CD: Publish to GHCR
├── docker-compose.yml
├── Dockerfile
├── pyproject.toml
└── README.md
```

## 🔧 Configuration

### Profile Example (`config/learning.yaml`)
```yaml
profiles:
  - name: avi-cohen
    description: "Avi Cohen's professional profile"
    documents:
      - type: json
        path: /app/data/persons/avi_profile.json
    embedding:
      backend:
        primary: ollama
        fallback: cloudflare
      model: nomic-embed-text
      dim: 768
    vectordb:
      url: http://vector-db:6333
      collection: avi-cohen-docs
    chunking:
      strategy: sentence
      max_tokens: 256
    autogen_hints:
      labels: ["profile", "skills", "experience"]
```

### Environment Variables
| Variable | Default | Description |
|----------|---------|-------------|
| `MCP_PORT` | 8013 | MCP server port |
| `JOB_PORT` | 8014 | Job server port |
| `MCP_TRANSPORT` | http | Transport type (http recommended) |
| `VECTOR_DB_URL` | http://vector-db:6333 | Qdrant URL |
| `OLLAMA_HOST` | http://localhost:11434 | Ollama server |
| `EMBED_MODEL` | nomic-embed-text | Embedding model |
| `USE_AUTOGEN` | 0 | Enable AutoGen (0 or 1) |
| `EMBED_CONCURRENCY` | 2 | Concurrent embeddings |
| `EMBED_PACING_MS` | 150 | Rate limit delay (ms) |

## 🐛 Troubleshooting

### MCP Server Won't Start
```powershell
# Check logs
docker compose logs learning-mcp | Select-String "mcp_server"

# Verify config loads
docker compose exec learning-mcp python -c "from mcp_server import mcp; print('OK')"
```

### Job Server Database Errors
```powershell
# Reset database
docker compose exec learning-mcp rm /app/state/jobs.db
docker compose restart learning-mcp
```

### Tests Failing
```powershell
# Rebuild with test dependencies
docker compose build learning-mcp --no-cache
docker compose up -d

# Run specific test
docker compose exec learning-mcp python -m pytest tests/test_core/test_embeddings.py::test_embed_batch_texts -v
```

### Embedding Dimension Mismatch
Ensure `profile.embedding.dim` matches your model's actual output:
```powershell
# Test embedding
curl http://localhost:8014/debug/embed
```

## 📚 Documentation

- **Developer Guide**: See `.github/copilot-instructions.md` for conventions
- **API Docs**: http://localhost:8014/docs (Swagger UI)
- **MCP Tools**: Use MCP Inspector at http://localhost:8013/mcp
- **Test README**: `tests/README.md` for testing instructions

## 🤝 Contributing

1. **Fork** the repository
2. **Create** a feature branch: `git checkout -b feature/amazing-feature`
3. **Write tests** for new functionality
4. **Run tests**: `docker compose exec learning-mcp pytest tests/`
5. **Commit**: `git commit -m 'Add amazing feature'`
6. **Push**: `git push origin feature/amazing-feature`
7. **Open** a Pull Request

### Code Standards
- Black formatting (line length 100)
- Type hints for public functions
- Docstrings for modules and classes
- Test coverage >70% for new code

## 📄 License

MIT License - see LICENSE file for details

## 🙏 Acknowledgments

- **fastmcp**: Modern MCP server framework
- **Qdrant**: High-performance vector database
- **Ollama**: Local embedding inference
- **AutoGen**: Multi-agent conversation framework
- **FastAPI**: Modern Python web framework

## 📞 Support

- **Issues**: https://github.com/aviciot/learning-mcp/issues
- **Discussions**: https://github.com/aviciot/learning-mcp/discussions
- **Email**: avi@example.com

---

**Built with ❤️ by Avi Cohen** | [GitHub](https://github.com/aviciot) | [LinkedIn](https://linkedin.com/in/avicohen)
