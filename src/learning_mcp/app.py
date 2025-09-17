# src/learning_mcp/app.py
"""
Main FastAPI app for Learning MCP.
"""

from fastapi import FastAPI

from learning_mcp.routes.health import router as health_router
from learning_mcp.routes.ingest import router as ingest_router
from learning_mcp.routes.search import router as search_router
from learning_mcp.routes.embed_sample import router as embed_sample_router
from learning_mcp.routes.config_route import router as config_router

app = FastAPI(
    title="Learning MCP",
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_tags=[
        {"name": "health", "description": "Service health checks"},
        {"name": "ingest", "description": "Ingest PDF documents into vector DB"},
        {"name": "search", "description": "Semantic search over ingested docs"},
        {"name": "config", "description": "Configuration and profile diagnostics"},
    ],
)

# routers
app.include_router(health_router, prefix="", tags=["health"])
app.include_router(ingest_router, prefix="", tags=["ingest"])
app.include_router(search_router, prefix="", tags=["search"])
app.include_router(config_router, prefix="", tags=["config"])
app.include_router(embed_sample_router, prefix="")
