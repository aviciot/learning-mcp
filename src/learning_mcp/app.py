"""
Main FastAPI app with MCP integration for Learning MCP.
Run via Docker Compose (see docker-compose.yml) or manually:
  uvicorn learning_mcp.app:app --host 0.0.0.0 --port 8013 --reload
"""
import logging
from fastapi import FastAPI
from fastapi.openapi.utils import get_openapi
from learning_mcp.config import settings
from learning_mcp.routes.health import router as health_router
from learning_mcp.routes.ingest import router as ingest_router
from learning_mcp.routes.search import router as search_router

# ✅ import API Agent router (not plan_with_autogen)
from learning_mcp.routes.api_agent import router as api_agent_router

from learning_mcp.routes.embed_sample import router as embed_sample_router
from learning_mcp.routes.config_route import router as config_router
from learning_mcp.routes import jobs as jobs_routes
# MCP endpoints
from learning_mcp.routes.api_exec import router as api_exec_router
from learning_mcp.routes.search_api import router as search_api_router
from learning_mcp.routes.api_plan import router as api_plan_router
from learning_mcp.routes.echo import router as echo_route


from contextlib import asynccontextmanager
import httpx, os, asyncio

VECTOR_DB_URL = os.getenv("VECTOR_DB_URL", "http://vector-db:6333").rstrip("/")

# ---------- Logging ----------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
logger = logging.getLogger("learning_mcp")
logger.info("Learning MCP app starting up")


@asynccontextmanager
async def lifespan(app):
    # startup: wait for Qdrant
    readyz = f"{VECTOR_DB_URL}/readyz"
    for attempt in range(1, 31):
        try:
            async with httpx.AsyncClient(timeout=2.0) as client:
                r = await client.get(readyz)
            if r.status_code == 200:
                logger.info("Vector DB ready: %s", VECTOR_DB_URL)
                break
        except Exception as e:
            logger.warning("Vector DB not ready (try %s/30): %s", attempt, e)
        await asyncio.sleep(1)
    else:
        logger.error("Vector DB not reachable after retries: %s", VECTOR_DB_URL)
    yield


# ---------- FastAPI ----------
app = FastAPI(
    title="Learning MCP",
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
    openapi_tags=[
        {"name": "health", "description": "Service health checks"},
        {"name": "ingest", "description": "Ingest PDF documents into vector DB"},
        {"name": "search", "description": "Semantic search over ingested docs (incl. API-context hints)"},
        {"name": "config", "description": "Configuration and profile diagnostics"},
        {"name": "monitoring", "description": "Ingest job monitoring (list & detail)"},
    ],
)

# ---------- OpenAPI Customization ----------
def _profile_names():
    try:
        cfg = settings.load_profiles()
        return [p.get("name") for p in (cfg.get("profiles") or []) if p.get("name")]
    except Exception as e:
        logger.error(f"Failed to load profiles: {e}")
        return []

def custom_openapi():
    """
    Patch the auto-generated OpenAPI schema so that any request model with a
    `profile` field shows a dropdown of valid profile names in Swagger UI.

    Why:
        By default, Pydantic defines `profile` as a plain string, so Swagger
        renders it as a free text box. However, our profiles actually come
        from `learning.yaml` (dynamic, environment-specific). We want Swagger
        to show those as selectable options to reduce typos and guide the user.

    How:
        - Build the normal OpenAPI schema with `get_openapi`.
        - Iterate over all schema components (`components.schemas`).
        - If a schema has a `profile` property, inject:
            • enum = list of profile names from `learning.yaml`
            • description = "Profile from learning.yaml"
        - Assign the patched schema back to `app.openapi_schema`.

    Impact:
        * Swagger UI (`/docs`) will now show a dropdown for `profile` on both
          `/api_context` and `/api_request` endpoints.
        * Runtime validation is unchanged: unknown profiles are still rejected
          in `_get_profile_cfg`. This is purely a developer-experience aid.
        * MCP Inspector does not use this schema, so it is unaffected.
    """
    if app.openapi_schema:
        return app.openapi_schema
    openapi_schema = get_openapi(
        title=app.title,
        version=app.version,
        routes=app.routes,
    )
    profile_names = _profile_names()
    if not profile_names:
        logger.warning("No profiles found for OpenAPI schema")
        return openapi_schema

    for schema in openapi_schema.get("components", {}).get("schemas", {}).values():
        props = schema.get("properties", {})
        if "profile" in props:
            props["profile"]["enum"] = profile_names
            props["profile"]["description"] = "Profile from learning.yaml"
            logger.debug(f"Patched OpenAPI schema for 'profile' with options: {profile_names}")

    app.openapi_schema = openapi_schema
    return app.openapi_schema


app.openapi = custom_openapi

# ---------- Routers ----------
app.include_router(health_router, prefix="", tags=["health"])
app.include_router(ingest_router, prefix="", tags=["ingest"])
app.include_router(search_router, prefix="", tags=["search"])
app.include_router(search_api_router, prefix="", tags=["api"])
app.include_router(api_exec_router, prefix="", tags=["api"])
app.include_router(api_plan_router, prefix="", tags=["api"])
app.include_router(config_router, prefix="", tags=["config"])
app.include_router(embed_sample_router, prefix="")
app.include_router(jobs_routes.router, prefix="", tags=["monitoring"])
app.include_router(api_agent_router, prefix="/agent", tags=["agent"])  # ✅ fixed
app.include_router(echo_route, prefix="/echo", tags=["api"])

logger.info("Routers registered: health, ingest, search, search_api, config, embed_sample, jobs, agent")

# ---------- MCP Integration ----------
try:
    from fastapi_mcp import FastApiMCP

    mcp = FastApiMCP(app,
                     include_operations=["echo", "api_context", "api_request", "api_plan"]
                     )
    mcp.mount_http(mount_path="/mcp")  # 👈 HTTP transport at /mcp (recommended)
    logger.info("MCP HTTP server mounted at /mcp")
except Exception as e:
    logger.warning("MCP not mounted: %s", e)
