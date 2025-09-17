# Learning MCP

Learning MCP is a FastAPI service that indexes PDF manuals into a Qdrant vector database and exposes semantic search endpoints.
It is designed for experimenting with Model Context Protocol (MCP) style workflows by wiring together PDF ingestion, text chunking, embedding, and retrieval APIs.

## Features
- PDF ingestion pipeline: extract text with `pypdf`, chunk content, generate embeddings, and upsert into Qdrant.
- Pluggable embedding backends through environment or profile configuration (Ollama or Cloudflare Workers AI).
- Semantic search endpoint that returns scored snippets for a given query.
- Lightweight debug endpoint to validate embedding connectivity before a full ingest.
- Docker-based development workflow with live reload for the FastAPI app.

## Project Structure
- `config/learning.yaml` - profile definitions, vector DB and embedding settings
- `data/` - documents that are mounted read-only into the container
- `src/learning_mcp/` - FastAPI application code
- `docker-compose.yml` - local development wiring
- `Dockerfile` - production image definition
- `pyproject.toml` - Python package metadata and dependencies

## Requirements
- Python 3.12+ (for local development) or Docker with Compose.
- Access to a Qdrant instance; docker-compose expects one running at `http://vector-db:8080`.
- An embedding provider:
  - Ollama with a compatible embedding model (for example `nomic-embed-text`).
  - Cloudflare Workers AI account with API token and model ID (for example `@cf/baai/bge-small-en-v1.5`).
- PDF manuals or documents stored under `data/` matching the profile configuration.

## Environment Variables
Create a `.env` file (not committed to git) with values similar to:
```
PORT=8013
ENV=dev
VECTOR_DB_URL=http://vector-db:8080
EMBED_MODEL=nomic-embed-text
OLLAMA_HOST=http://host.docker.internal:11434
CF_ACCOUNT_ID=<your_account_id>
CF_API_TOKEN=<your_api_token>
CF_MODEL=@cf/baai/bge-small-en-v1.5
```
Adjust the values to match your local services. Environment variables override the YAML profile fields at runtime.

## Running with Docker Compose
```bash
docker compose up --build
```
This builds the image, mounts the source code for live reload, and starts the FastAPI app on http://localhost:8013.
Ensure your Qdrant instance and embedding provider are reachable from the container.

## Running Locally (without Docker)
```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .
uvicorn learning_mcp.app:app --reload --port 8013
```
Set the same environment variables as described above before starting the server.

## API Endpoints
| Method | Path           | Description |
| ------ | -------------- | ----------- |
| GET    | `/health`      | Service health check and profile summary. |
| GET    | `/profiles`    | List configured profiles and Qdrant status. |
| POST   | `/ingest`      | Ingest documents for a profile (extract -> chunk -> embed -> upsert). |
| POST   | `/search`      | Semantic search against ingested chunks for a profile. |
| GET    | `/debug/embed` | Returns embedding vector length for a sample text. |

Use the automatically generated Swagger UI at `/docs` for interactive requests.

## Profiles and Data
Profiles are defined in `config/learning.yaml`. A profile associates:
- A list of documents (relative paths under `/app/data` inside the container).
- Vector DB collection names and endpoint URL.
- Embedding provider configuration and chunking strategy.

Update the YAML file and restart the app (or trigger reload) after editing profiles.

## Next Steps
- Add additional profiles or document types.
- Extend the pipeline with metadata extraction or reranking.
- Integrate with an MCP client or agent to test contextual responses.
