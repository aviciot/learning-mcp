# Integrating External MCPs with Learning MCP

## Overview

This guide explains how we integrated GitHub functionality into Learning MCP by embedding an external MCP's capabilities directly into our service, creating a **unified MCP server**.

## The Challenge

**Original Problem:**
- Multiple MCP servers (Learning MCP + GitHub MCP)
- Complex orchestration
- Multiple endpoints to manage
- Client needs to connect to multiple services

**Our Solution:**
- Embed external functionality directly into Learning MCP
- Single endpoint for all tools
- Unified API surface
- Simpler client integration

---

## Architecture: Before vs After

### Before (Multiple MCPs)

```
┌─────────────────────────────────────┐
│  MCP Client (Omni API)              │
└──────────┬──────────────┬───────────┘
           │              │
           ↓              ↓
    ┌──────────┐   ┌─────────────┐
    │Learning  │   │  GitHub MCP │
    │   MCP    │   │  (separate) │
    │Port 8013 │   │  Port 8015  │
    └──────────┘   └─────────────┘
```

**Issues:**
- 2 endpoints to manage
- 2 services to deploy
- Complex routing logic in client
- Double maintenance burden

### After (Unified MCP)

```
┌─────────────────────────────────────┐
│  MCP Client (Omni API)              │
└──────────────────┬──────────────────┘
                   │
                   ↓
         ┌─────────────────────┐
         │  Learning MCP       │
         │  Port 8013          │
         │                     │
         │  Tools:             │
         │  ├─ search_docs     │
         │  ├─ plan_api_call   │
         │  ├─ search_github   │ ← NEW!
         │  ├─ get_github_file │ ← NEW!
         │  └─ list_github_repos│ ← NEW!
         └─────────────────────┘
```

**Benefits:**
- ✅ Single endpoint
- ✅ Unified tool namespace
- ✅ Simpler deployment
- ✅ One configuration

---

## Implementation Pattern

### Step 1: Create Integration Client

Instead of running GitHub MCP as a separate service, we created a **GitHub API client** that provides the same functionality:

```python
# src/learning_mcp/github_client.py

class GitHubClient:
    """Direct GitHub API integration (no external MCP needed)"""
    
    async def search_repositories(self, query: str, limit: int = 10):
        """Call GitHub API directly"""
        async with httpx.AsyncClient() as client:
            response = await client.get(
                "https://api.github.com/search/repositories",
                headers={"Authorization": f"token {self.token}"},
                params={"q": query, "per_page": limit}
            )
            return response.json()
```

**Key Insight:** Instead of wrapping the GitHub MCP, we replicated its functionality by calling the GitHub API directly.

### Step 2: Add Tools to MCP Server

Added new tools to our existing MCP server:

```python
# src/mcp_server.py

from learning_mcp.github_client import GitHubClient

# Initialize GitHub client
_github_client = GitHubClient()

@mcp.tool
async def search_github_repos(
    query: str,
    limit: int = 10,
    ctx: Context = None
) -> dict:
    """Search GitHub repositories"""
    repos = await _github_client.search_repositories(query, limit)
    return {"repositories": repos}

@mcp.tool
async def get_github_file(
    owner: str,
    repo: str,
    path: str,
    ctx: Context = None
) -> dict:
    """Get file contents from GitHub"""
    content = await _github_client.get_file_contents(owner, repo, path)
    return content
```

### Step 3: Configuration

Add credentials to environment:

```bash
# .env
GITHUB_PERSONAL_ACCESS_TOKEN=ghp_your_token_here
```

```yaml
# docker-compose.yml
services:
  learning-mcp:
    environment:
      - GITHUB_PERSONAL_ACCESS_TOKEN=${GITHUB_PERSONAL_ACCESS_TOKEN}
```

---

## Integration Strategies

### Strategy 1: Direct API Integration (What We Did)

**When to use:**
- External service has a REST API
- MCP just wraps API calls
- You want full control

**Pros:**
- ✅ No extra processes
- ✅ Direct control
- ✅ Simpler deployment
- ✅ Better performance

**Cons:**
- ❌ Need to implement API client
- ❌ Maintain API integration yourself

**Example:** GitHub MCP → GitHub API client

### Strategy 2: Subprocess Wrapper

**When to use:**
- External MCP has unique functionality
- No direct API available
- MCP has complex logic worth reusing

**Implementation:**
```python
import subprocess
import json

class ExternalMCPWrapper:
    def __init__(self, command: str, args: list):
        self.process = subprocess.Popen(
            [command] + args,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            text=True
        )
    
    async def call_tool(self, name: str, arguments: dict):
        """Forward tool call to external MCP via stdio"""
        request = {
            "jsonrpc": "2.0",
            "method": "tools/call",
            "params": {"name": name, "arguments": arguments}
        }
        self.process.stdin.write(json.dumps(request) + "\n")
        self.process.stdin.flush()
        response = json.loads(self.process.stdout.readline())
        return response["result"]

# Usage in MCP server
external_mcp = ExternalMCPWrapper("npx", ["-y", "@some/mcp-server"])

@mcp.tool
async def external_search(query: str):
    return await external_mcp.call_tool("search", {"q": query})
```

**Pros:**
- ✅ Reuse existing MCP functionality
- ✅ No reimplementation needed

**Cons:**
- ❌ Extra process overhead
- ❌ Complex error handling
- ❌ Stdio communication complexity

### Strategy 3: HTTP Proxy

**When to use:**
- External MCP uses HTTP transport
- Want loose coupling
- Need to run MCP separately anyway

**Implementation:**
```python
import httpx

class MCPHttpProxy:
    def __init__(self, base_url: str):
        self.base_url = base_url
    
    async def call_tool(self, name: str, arguments: dict):
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.base_url}/tools/call",
                json={"name": name, "arguments": arguments}
            )
            return response.json()

# Usage
other_mcp = MCPHttpProxy("http://localhost:8015")

@mcp.tool
async def proxied_search(query: str):
    return await other_mcp.call_tool("search", {"query": query})
```

**Pros:**
- ✅ Keep services separate
- ✅ Independent scaling
- ✅ Language-agnostic

**Cons:**
- ❌ Network overhead
- ❌ Multiple deployments
- ❌ Service discovery needed

---

## Decision Matrix

| Factor | Direct API | Subprocess | HTTP Proxy |
|--------|-----------|------------|------------|
| **Performance** | ⭐⭐⭐⭐⭐ Fast | ⭐⭐⭐ Medium | ⭐⭐ Slow (network) |
| **Simplicity** | ⭐⭐⭐⭐ Simple | ⭐⭐ Complex | ⭐⭐⭐ Medium |
| **Maintenance** | ⭐⭐⭐ You maintain | ⭐⭐⭐⭐⭐ Reuse external | ⭐⭐⭐⭐ Reuse external |
| **Deployment** | ⭐⭐⭐⭐⭐ Single service | ⭐⭐⭐⭐ Single container | ⭐⭐ Multiple services |
| **Reliability** | ⭐⭐⭐⭐⭐ Stable | ⭐⭐⭐ Process management | ⭐⭐⭐ Network issues |

**Our Choice:** Direct API (Strategy 1) because:
- GitHub has a simple REST API
- No complex logic to reuse
- Best performance
- Simplest deployment

---

## Best Practices

### 1. **Choose Integration Strategy Based on Complexity**

```
Simple API → Direct integration (Strategy 1)
Complex MCP → Subprocess wrapper (Strategy 2)
Remote service → HTTP proxy (Strategy 3)
```

### 2. **Keep Credentials Secure**

```bash
# .env (not committed)
EXTERNAL_SERVICE_TOKEN=secret

# docker-compose.yml
environment:
  - EXTERNAL_SERVICE_TOKEN=${EXTERNAL_SERVICE_TOKEN}
```

### 3. **Add Error Handling**

```python
@mcp.tool
async def external_tool(query: str):
    try:
        result = await external_client.call(query)
        return result
    except Exception as e:
        log.error(f"External service error: {e}")
        return {"error": str(e), "fallback": "default_value"}
```

### 4. **Document Tool Availability**

```python
@mcp.tool
async def search_github_repos(query: str):
    """
    Search GitHub repositories.
    
    NOTE: Requires GITHUB_PERSONAL_ACCESS_TOKEN environment variable.
    If token not provided, API calls will be rate-limited (60/hour).
    """
```

### 5. **Add Health Checks**

```python
async def check_external_service():
    """Verify external service is accessible"""
    try:
        await github_client.list_user_repos("test", limit=1)
        return True
    except:
        return False
```

---

## Example: Adding Another External MCP

Let's say you want to add **Brave Search MCP**:

### Step 1: Analyze the MCP

```bash
# Check what tools Brave Search MCP provides
npx -y @modelcontextprotocol/server-brave-search --help
```

### Step 2: Decide Strategy

**Option A:** Direct API (if Brave has API)
```python
# brave_client.py
class BraveSearchClient:
    async def web_search(self, query: str):
        async with httpx.AsyncClient() as client:
            response = await client.get(
                "https://api.search.brave.com/res/v1/web/search",
                headers={"X-Subscription-Token": self.token},
                params={"q": query}
            )
            return response.json()
```

**Option B:** Subprocess wrapper
```python
brave_mcp = ExternalMCPWrapper("npx", [
    "-y",
    "@modelcontextprotocol/server-brave-search"
])
```

### Step 3: Add to MCP Server

```python
# mcp_server.py
from learning_mcp.brave_client import BraveSearchClient

brave = BraveSearchClient()

@mcp.tool
async def web_search(query: str, limit: int = 10):
    """Search the web using Brave Search"""
    results = await brave.web_search(query)
    return {"results": results[:limit]}
```

### Step 4: Configure

```bash
# .env
BRAVE_API_KEY=your_brave_api_key
```

### Step 5: Test

```python
# Test the integration
result = await mcp.call_tool("web_search", {"query": "RAG systems"})
```

---

## Testing Integrated MCPs

### Unit Tests

```python
# tests/test_github_integration.py
import pytest
from learning_mcp.github_client import GitHubClient

@pytest.mark.asyncio
async def test_search_repositories():
    client = GitHubClient(token="test_token")
    repos = await client.search_repositories("python", limit=5)
    assert len(repos) <= 5
    assert all("name" in repo for repo in repos)
```

### Integration Tests

```python
# tests/test_mcp_tools.py
@pytest.mark.asyncio
async def test_github_search_tool():
    result = await mcp.call_tool("search_github_repos", {
        "query": "test",
        "limit": 5
    })
    assert "repositories" in result
    assert isinstance(result["repositories"], list)
```

### Manual Testing

```bash
# Test via MCP endpoint
curl -X POST http://localhost:8013/mcp \
  -H "Content-Type: application/json" \
  -d '{
    "method": "tools/call",
    "params": {
      "name": "search_github_repos",
      "arguments": {"query": "RAG", "limit": 5}
    }
  }'
```

---

## Monitoring & Debugging

### Add Logging

```python
@mcp.tool
async def search_github_repos(query: str, ctx: Context = None):
    if ctx:
        ctx.info(f"Searching GitHub: {query}")
    
    try:
        results = await github_client.search_repositories(query)
        if ctx:
            ctx.info(f"Found {len(results)} results")
        return results
    except Exception as e:
        log.error(f"GitHub search failed: {e}")
        if ctx:
            ctx.error(f"Search failed: {e}")
        raise
```

### Track Usage

```python
# Track which external services are used
usage_stats = {"github": 0, "brave": 0}

@mcp.tool
async def search_github_repos(query: str):
    usage_stats["github"] += 1
    log.info(f"GitHub API calls: {usage_stats['github']}")
    return await github_client.search_repositories(query)
```

---

## Summary

### What We Did

1. ✅ **Analyzed GitHub MCP** - Understood it just wraps GitHub API
2. ✅ **Created Direct Integration** - Built `GitHubClient` class
3. ✅ **Added MCP Tools** - Exposed 3 new tools in Learning MCP
4. ✅ **Configured Credentials** - Added token to `.env`
5. ✅ **Tested Integration** - Verified all tools work

### Key Takeaways

- **Direct API integration** is best when external service has simple REST API
- **Subprocess wrapper** for complex MCPs worth reusing
- **HTTP proxy** for services that must run separately
- **Always add error handling** and logging
- **Document dependencies** (tokens, credentials)

### Result

**One MCP server with 5 tools:**
- `search_docs` (yours)
- `plan_api_call` (yours)
- `search_github_repos` (integrated)
- `get_github_file` (integrated)
- `list_user_github_repos` (integrated)

**Single endpoint:** `http://localhost:8013/mcp` 🚀

---

## Next Steps

Want to integrate another external MCP? Follow these steps:

1. **Identify the MCP** - What functionality does it provide?
2. **Choose strategy** - Direct API, subprocess, or HTTP?
3. **Implement client** - Create integration code
4. **Add tools** - Expose in your MCP server
5. **Configure** - Add credentials/settings
6. **Test** - Verify it works
7. **Document** - Update this guide!

Happy integrating! 🎉
