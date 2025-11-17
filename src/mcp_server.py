"""Learning MCP V2.0 - MCP Server for AI Agent Interactions."""

import logging
import os
from typing import Optional, List

from fastmcp import FastMCP, Context

# Core logic imports
from learning_mcp.config import get_config, get_profile, settings
from learning_mcp.embeddings import Embedder, EmbeddingConfig
from learning_mcp.vdb import VDB
from learning_mcp.github_client import GitHubClient

# Configure logging to show all INFO level messages including emojis
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(name)s] %(levelname)s: %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

log = logging.getLogger("learning_mcp.mcp_server")

# Initialize MCP server
mcp = FastMCP("learning-mcp-server", dependencies=["qdrant-client", "httpx", "pypdf"])

# Get enabled tools from configuration
enabled_tools = settings.get_enabled_mcp_tools()
log.info(f"Enabled MCP tools: {', '.join(enabled_tools)}")

# Initialize GitHub client (optional - only if token provided)
_github_client = None

def _get_github_client() -> GitHubClient:
    """Get or create GitHub client"""
    global _github_client
    if _github_client is None:
        _github_client = GitHubClient()
    return _github_client


def _get_embedder(prof: dict) -> Embedder:
    """Create embedder from profile config."""
    ecfg = EmbeddingConfig.from_profile(prof)
    return Embedder(ecfg)


def _get_vdb(prof: dict) -> VDB:
    """Create VDB instance from profile config."""
    vcfg = prof.get("vectordb", {}) or {}
    ecfg = EmbeddingConfig.from_profile(prof)
    
    return VDB(
        url=vcfg.get("url"),
        collection=vcfg.get("collection"),
        dim=ecfg.dim,
        distance=vcfg.get("distance", "cosine")
    )


# Conditionally register tools based on configuration
if "search_docs" in enabled_tools:
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
        embedder = _get_embedder(prof)
        vdb = _get_vdb(prof)
        
        # Embed query
        query_vecs = await embedder.embed([q])
        query_vec = query_vecs[0]
        
        # Search Qdrant
        vcfg = prof.get("vectordb", {}) or {}
        collection = vcfg.get("collection", profile)
        results = vdb.search(
            query_vec=query_vec,
            top_k=min(top_k, 20)
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


if "list_profiles" in enabled_tools:
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


if "plan_api_call" in enabled_tools:
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
            await ctx.info(f"Planning API call for goal: {goal}")
        
        # Search for relevant docs (call helper directly, not the decorated tool)
        prof = get_profile(profile)
        embedder = _get_embedder(prof)
        vdb = _get_vdb(prof)
        
        try:
            # Embed query
            query_vecs = await embedder.embed([goal])
            query_vec = query_vecs[0]
            
            # Search Qdrant
            results = vdb.search(query_vec=query_vec, top_k=10)
            
            # Format results for AutoGen
            context_chunks = [r.payload.get("text", "") for r in results]
            
            if ctx:
                await ctx.info(f"Found {len(results)} relevant docs")
        finally:
            await embedder.close()
        
        # Use AutoGen planner
        plan = await plan_with_autogen(
            q=goal,
            profile=profile
        )
        
        if ctx:
            await ctx.info(f"Generated plan: {plan.get('endpoint', 'N/A')}")
        
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


# ============================================================================
# GitHub Tools
# ============================================================================

if "search_github_repos" in enabled_tools:
    @mcp.tool
    async def search_github_repos(
        query: str,
        profile: str = "avi-cohen",
        limit: int = 10,
        sort: str = "stars",
        ctx: Context = None
    ) -> dict:
        """
        Search GitHub repositories (scoped to profile's GitHub user by default).
        
        Use this to find repositories by keywords, topics, or usernames.
        If the profile has a github.username configured, it will automatically
        scope searches to that user unless you specify a different user: or org:
        
        Args:
            query: Search keywords (e.g., "RAG", "machine learning")
            profile: Profile name (uses github.username from config if available)
            limit: Maximum number of results to return (default 10, max 30)
            sort: Sort results by 'stars', 'forks', or 'updated' (default 'stars')
        
        Returns:
            dict with 'repositories' list containing name, description, url, stars, etc.
        
        Examples:
            - query="RAG", profile="avi-cohen" → searches "RAG user:aviciot" (auto-scoped)
            - query="RAG user:microsoft" → explicit user override
            - query="machine learning language:python" → searches all GitHub
        """
        # Load profile config and get GitHub username
        try:
            prof = get_profile(profile)
            github_username = prof.get("github", {}).get("username")
            
            # Auto-inject username if configured and not already in query
            if github_username and "user:" not in query and "org:" not in query:
                query = f"{query} user:{github_username}"
                if ctx:
                    ctx.info(f"Auto-scoped to user: {github_username}")
        except Exception as e:
            log.warning(f"Could not load profile '{profile}': {e}")
            # Continue without profile scoping
        
        if ctx:
            ctx.info(f"Searching GitHub for: {query}")
        
        try:
            github = _get_github_client()
            repos = await github.search_repositories(
                query=query,
                limit=min(limit, 30),
                sort=sort
            )
            
            if ctx:
                ctx.info(f"Found {len(repos)} repositories")
            
            return {
                "query": query,
                "profile": profile,
                "count": len(repos),
                "repositories": repos
            }
        except Exception as e:
            log.error(f"GitHub search error: {e}")
            return {
                "error": str(e),
                "query": query,
                "repositories": []
            }


if "get_github_file" in enabled_tools:
    @mcp.tool
    async def get_github_file(
        owner: str,
        repo: str,
        path: str,
        ref: str = "main",
        ctx: Context = None
    ) -> dict:
        """
        Get contents of a file from a GitHub repository.
        
        Use this to read README files, source code, documentation, or any file from a repo.
        
        Args:
            owner: Repository owner (username or organization)
            repo: Repository name
            path: Path to file (e.g., "README.md", "src/main.py")
            ref: Branch, tag, or commit SHA (default "main")
        
        Returns:
            dict with file content and metadata (name, path, size, url)
        
        Examples:
            - owner="aviciot", repo="learning-mcp", path="README.md"
            - owner="microsoft", repo="autogen", path="docs/index.md"
        """
        if ctx:
            ctx.info(f"Fetching {owner}/{repo}/{path} (ref: {ref})")
        
        try:
            github = _get_github_client()
            file_data = await github.get_file_contents(
                owner=owner,
                repo=repo,
                path=path,
                ref=ref
            )
            
            if ctx:
                ctx.info(f"Retrieved file: {file_data['size']} bytes")
            
            return file_data
        except Exception as e:
            log.error(f"Error fetching GitHub file: {e}")
            return {
                "error": str(e),
                "owner": owner,
                "repo": repo,
                "path": path
            }


if "list_user_github_repos" in enabled_tools:
    @mcp.tool
    async def list_user_github_repos(
        profile: str = "avi-cohen",
        limit: int = 30,
        type_filter: str = "all",
        ctx: Context = None
    ) -> dict:
        """
        List repositories for the profile's GitHub user.
        
        Use this to get an overview of all repos owned by a user or organization.
        Uses the github.username configured in the profile.
        
        Args:
            profile: Profile name (uses github.username from config)
            limit: Maximum number of repos to return (default 30, max 100)
            type_filter: Filter by 'all', 'owner' (repos user owns), or 'member' (repos user contributes to)
        
        Returns:
            dict with 'repositories' list sorted by most recently updated
        
        Examples:
            - profile="avi-cohen", limit=50 → lists repos for aviciot
            - profile="company-docs" → lists repos for company's GitHub user
        """
        # Load profile config and get GitHub username
        try:
            prof = get_profile(profile)
            github_username = prof.get("github", {}).get("username")
            
            if not github_username:
                return {
                    "error": f"Profile '{profile}' has no github.username configured",
                    "profile": profile,
                    "repositories": []
                }
        except Exception as e:
            log.error(f"Could not load profile '{profile}': {e}")
            return {
                "error": f"Profile '{profile}' not found",
                "profile": profile,
                "repositories": []
            }
        
        if ctx:
            ctx.info(f"Listing repositories for user: {github_username} (profile: {profile})")
        
        try:
            github = _get_github_client()
            repos = await github.list_user_repos(
                username=github_username,
                limit=min(limit, 100),
                type_filter=type_filter
            )
            
            if ctx:
                ctx.info(f"Found {len(repos)} repositories")
            
            return {
                "username": github_username,
                "profile": profile,
                "count": len(repos),
                "repositories": repos
            }
        except Exception as e:
            log.error(f"Error listing user repos: {e}")
            return {
                "error": str(e),
                "username": github_username,
                "profile": profile,
                "repositories": []
            }


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
