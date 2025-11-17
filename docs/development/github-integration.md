# GitHub Integration for Learning MCP

## Overview

GitHub tools are now integrated directly into Learning MCP! No separate service needed.

## New Tools Available

### 1. `search_github_repos`
Search GitHub repositories by keywords, topics, or users.

**Example:**
```json
{
  "tool": "search_github_repos",
  "arguments": {
    "query": "RAG user:aviciot",
    "limit": 10,
    "sort": "stars"
  }
}
```

**Response:**
```json
{
  "count": 3,
  "repositories": [
    {
      "name": "learning-mcp",
      "description": "RAG system with MCP integration",
      "url": "https://github.com/aviciot/learning-mcp",
      "stars": 15,
      "language": "Python",
      "topics": ["rag", "mcp", "qdrant"]
    }
  ]
}
```

### 2. `get_github_file`
Read any file from a GitHub repository.

**Example:**
```json
{
  "tool": "get_github_file",
  "arguments": {
    "owner": "aviciot",
    "repo": "learning-mcp",
    "path": "README.md"
  }
}
```

**Response:**
```json
{
  "name": "README.md",
  "content": "# Learning MCP\n\n...",
  "size": 5420,
  "url": "https://github.com/aviciot/learning-mcp/blob/main/README.md"
}
```

### 3. `list_user_github_repos`
List all repositories for a user or organization.

**Example:**
```json
{
  "tool": "list_user_github_repos",
  "arguments": {
    "username": "aviciot",
    "limit": 30
  }
}
```

## Setup

### 1. Get GitHub Personal Access Token

1. Go to: https://github.com/settings/tokens
2. Click "Generate new token (classic)"
3. Select scopes:
   - `public_repo` (for public repos)
   - `repo` (for private repos - optional)
4. Copy the token: `ghp_xxxxxxxxxxxxx`

### 2. Add to `.env` File

```bash
# Add this line to your .env file
GITHUB_PERSONAL_ACCESS_TOKEN=ghp_your_token_here
```

### 3. Restart Docker

```powershell
docker compose restart learning-mcp
```

## Testing

```powershell
# Test GitHub search
curl -X POST http://localhost:8013/mcp `
  -H "Content-Type: application/json" `
  -d '{
    "method": "tools/call",
    "params": {
      "name": "search_github_repos",
      "arguments": {
        "query": "RAG user:aviciot",
        "limit": 5
      }
    }
  }'
```

## Usage in Your Omni API

```python
import httpx

async def search_user_content(query: str):
    """Search both documents AND GitHub repos"""
    
    async with httpx.AsyncClient() as client:
        # Search your documents
        docs = await client.post(
            "http://localhost:8013/mcp",
            json={
                "method": "tools/call",
                "params": {
                    "name": "search_docs",
                    "arguments": {
                        "query": query,
                        "profile": "avi-cohen",
                        "top_k": 5
                    }
                }
            }
        )
        
        # Search GitHub repos
        repos = await client.post(
            "http://localhost:8013/mcp",
            json={
                "method": "tools/call",
                "params": {
                    "name": "search_github_repos",
                    "arguments": {
                        "query": f"{query} user:aviciot",
                        "limit": 5
                    }
                }
            }
        )
        
        # Combine results
        return {
            "documents": docs.json(),
            "repositories": repos.json()
        }
```

## Benefits

✅ **Single service** - No separate GitHub MCP needed  
✅ **Same endpoint** - All tools at `http://localhost:8013/mcp`  
✅ **Simple config** - Just add GitHub token to `.env`  
✅ **Fast** - Direct GitHub API calls, no intermediate service  
✅ **Integrated** - Use alongside your existing search_docs and plan_api_call tools  

## Rate Limits

- **With token**: 5,000 requests/hour
- **Without token**: 60 requests/hour (not recommended)

Always provide a token for production use!

## Examples

### Find RAG Projects
```
Query: "Show me RAG projects"
→ Calls: search_github_repos("RAG user:aviciot")
→ Returns: learning-mcp, other-rag-project, etc.
```

### Get README
```
Query: "What's in the learning-mcp README?"
→ Calls: get_github_file("aviciot", "learning-mcp", "README.md")
→ Returns: Full README content
```

### List All Repos
```
Query: "List all my repositories"
→ Calls: list_user_github_repos("aviciot")
→ Returns: All your repos sorted by update date
```

## Next Steps

1. Add GitHub token to `.env`
2. Restart Docker
3. Test the tools
4. Integrate into your Omni API!

🚀 Now you have ONE MCP server with everything!
