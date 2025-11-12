"""Learning MCP V2.0 - MCP Server for AI Agent Interactions."""

import logging
import os
from typing import Optional

from fastmcp import FastMCP, Context

# Core logic imports
from learning_mcp.config import get_config, get_profile
from learning_mcp.embeddings import Embedder
from learning_mcp.vdb import VDB

log = logging.getLogger("learning_mcp.mcp_server")

# Initialize MCP server
mcp = FastMCP("learning-mcp-server", dependencies=["qdrant-client", "httpx", "pypdf"])

# Global state (lazy-loaded)
_embedder: Optional[Embedder] = None
_vdb: Optional[VDB] = None


def _get_embedder() -> Embedder:
    """Lazy-load embedder singleton."""
    global _embedder
    if _embedder is None:
        _embedder = Embedder()
    return _embedder


def _get_vdb() -> VDB:
    """Lazy-load VDB singleton."""
    global _vdb
    if _vdb is None:
        _vdb = VDB()
    return _vdb


@mcp.tool
async def search_docs(
    q: str,
    profile: str,
    top_k: int = 5,
    ctx: Context = None
) -> dict:
    """
    Semantic search over documents in a profile's collection.
    
    Args:
        q: Natural language query
        profile: Profile name (e.g., 'avi-cohen', 'dahua-camera')
        top_k: Number of results to return (default 5, max 20)
    
    Returns:
        dict with 'results' (list of scored chunks) and 'metadata'
    """
    if ctx:
        ctx.info(f"Searching profile '{profile}' for: {q[:50]}...")
    
    prof = get_profile(profile)
    embedder = _get_embedder()
    vdb = _get_vdb()
    
    # Embed query
    query_vec = await embedder.embed_single(q)
    
    # Search Qdrant
    collection = prof.vectordb.collection
    results = await vdb.search(
        collection=collection,
        query_vector=query_vec,
        limit=min(top_k, 20),
        score_threshold=prof.search.get("score_threshold", 0.5)
    )
    
    if ctx:
        ctx.info(f"Found {len(results)} results")
    
    return {
        "results": [
            {
                "text": r.payload.get("text"),
                "score": r.score,
                "metadata": {
                    "doc_id": r.payload.get("doc_id"),
                    "chunk_idx": r.payload.get("chunk_idx"),
                    "source": r.payload.get("doc_path")
                }
            }
            for r in results
        ],
        "metadata": {
            "profile": profile,
            "collection": collection,
            "top_k": top_k,
            "query": q
        }
    }


@mcp.tool
async def list_profiles() -> dict:
    """
    List all available profiles from learning.yaml.
    
    Returns:
        dict with 'profiles' list containing name, description, doc count
    """
    cfg = get_config()
    profiles_list = cfg.get("profiles", [])
    
    profiles = []
    for prof in profiles_list:
        profiles.append({
            "name": prof.get("name", ""),
            "description": prof.get("description", ""),
            "document_count": len(prof.get("documents", [])),
            "embedding_backend": prof.get("embedding", {}).get("backend", {}).get("primary", "unknown"),
            "collection": prof.get("vectordb", {}).get("collection", prof.get("name", ""))
        })
    
    return {"profiles": profiles}


@mcp.tool
async def plan_api_call(
    goal: str,
    profile: str,
    ctx: Context = None
) -> dict:
    """
    Use AutoGen to plan an API call based on documentation search.
    OPTIONAL: Only available if USE_AUTOGEN=1 env var is set.
    
    Args:
        goal: What you want to accomplish (e.g., "enable wifi on camera")
        profile: Profile to search for API docs
    
    Returns:
        dict with 'method', 'endpoint', 'params', 'reasoning'
    """
    if not os.getenv("USE_AUTOGEN", "0") == "1":
        return {
            "status": "disabled",
            "message": "AutoGen is disabled. Set USE_AUTOGEN=1 to enable API planning."
        }
    
    # Lazy import (optional dependency)
    try:
        from learning_mcp.agents.autogen_planner import plan_with_autogen
    except ImportError:
        return {
            "status": "not_installed",
            "message": "AutoGen dependencies not installed. Run: pip install pyautogen"
        }
    
    if ctx:
        ctx.info(f"Planning API call for goal: {goal}")
    
    # Search for relevant docs
    search_results = await search_docs(q=goal, profile=profile, top_k=10, ctx=ctx)
    
    # Use AutoGen planner
    plan = await plan_with_autogen(
        goal=goal,
        context_chunks=[r["text"] for r in search_results["results"]],
        profile=profile
    )
    
    if ctx:
        ctx.info(f"Generated plan: {plan.get('endpoint', 'N/A')}")
    
    return plan


@mcp.resource("profile://{name}")
async def get_profile_config(name: str) -> str:
    """
    Get full YAML configuration for a specific profile.
    
    Args:
        name: Profile name
    
    Returns:
        YAML string of profile config
    """
    import yaml
    prof = get_profile(name)
    return yaml.dump(prof, default_flow_style=False)


if __name__ == "__main__":
    # Run with HTTP Streamable transport (recommended for production)
    # For Claude Desktop with stdio, use: fastmcp run src/mcp_server.py
    transport = os.getenv("MCP_TRANSPORT", "http")
    
    if transport == "http":
        port = int(os.getenv("MCP_PORT", 8013))
        log.info(f"Starting MCP server with HTTP Streamable transport on port {port}")
        log.info(f"MCP endpoint will be available at: http://0.0.0.0:{port}/mcp")
        mcp.run(transport="http", host="0.0.0.0", port=port)
    else:
        log.info("Starting MCP server with stdio transport")
        mcp.run(transport="stdio")
