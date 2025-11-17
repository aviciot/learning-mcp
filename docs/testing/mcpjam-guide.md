# mcpjam Testing Guide

Quick reference for testing Learning MCP tools in mcpjam playground chat.

## GitHub Tools

### 1. `list_user_github_repos` - List User's Repositories

**Purpose**: List all repositories for a GitHub user (uses profile's configured username)

**Example Questions:**

```
List my GitHub repositories
```

```
Show me the top 5 repositories for the avi-cohen profile
```

```
List repositories for avi-cohen profile, limit 10
```

```
What repositories does the avi-cohen profile have on GitHub?
```

```
Using the avi-cohen profile, show me my GitHub repositories
```

**Expected Tool Call:**
```json
{
  "profile": "avi-cohen",
  "limit": 10
}
```

**Expected Response:**
- Username loaded from profile (aviciot)
- List of repositories with name, URL, stars, language
- Most recently updated repos first

---

### 2. `search_github_repos` - Search Repositories (with Auto-Scoping)

**Purpose**: Search GitHub repositories (automatically scopes to profile's user if configured)

**Example Questions:**

**Auto-scoping (searches your repos):**
```
Search for RAG projects in my repositories
```

```
Find my Python projects related to APIs
```

```
Search for machine learning repositories in my GitHub
```

```
Find MCP-related projects on my GitHub account
```

**Search other users/orgs:**
```
Search for Microsoft's TypeScript repositories
```

```
Find Python RAG projects by user:openai
```

```
Search for vector database projects on GitHub
```

**With profile explicitly:**
```
Using avi-cohen profile, search for Python projects
```

```
Search for RAG repositories using the avi-cohen profile
```

**Expected Tool Call (auto-scoped):**
```json
{
  "query": "RAG",
  "profile": "avi-cohen",
  "limit": 5
}
```

**What Happens:**
- Query "RAG" becomes "RAG user:aviciot" automatically
- Searches only your repositories by default
- Can override with explicit `user:` or `org:` in query

---

### 3. `get_github_file` - Get File Contents

**Purpose**: Retrieve contents of any file from a GitHub repository

**Example Questions:**

**Your repositories:**
```
Get the README.md file from my learning-mcp repository
```

```
Show me the mcp_server.py file from aviciot/learning-mcp
```

```
Read the learning.yaml file from my learning-mcp repo in the config folder
```

```
Get the package.json from my learning-mcp project
```

**Other repositories:**
```
Get the README from microsoft/autogen repository
```

```
Show me the main.py file from openai/gpt-3 repo
```

```
Read the LICENSE file from aviciot/learning-mcp
```

**Expected Tool Call:**
```json
{
  "owner": "aviciot",
  "repo": "learning-mcp",
  "path": "README.md",
  "ref": "main"
}
```

**Expected Response:**
- File name, size, URL
- Full file contents (text or base64-encoded)
- Metadata about the file

---

## Document Search Tools

### 4. `search_docs` - Semantic Search

**Purpose**: Search through ingested documents using semantic similarity

**Example Questions:**

**Informatica Cloud:**
```
Search for REST API documentation in informatica-cloud
```

```
Find information about authentication in the informatica-cloud profile
```

```
What does informatica-cloud say about connections?
```

```
Search informatica-cloud docs for workflow
```

```
How do I create a mapping in Informatica Cloud?
```

```
Find information about taskflows in informatica-cloud documentation
```

```
Search informatica-cloud for API rate limits
```

**Dahua Camera:**
```
Find information about WiFi settings in dahua-camera profile
```

```
Search dahua-camera profile for camera configuration
```

```
How do I enable audio on Dahua camera?
```

```
Look up network settings in dahua-camera documents
```

**Avi-Cohen Profile:**
```
Using avi-cohen profile, search for skills and experience
```

```
Search avi-cohen for programming languages
```

**Expected Tool Call:**
```json
{
  "q": "REST API documentation",
  "profile": "informatica-cloud",
  "top_k": 5
}
```

**Expected Response:**
- Ranked results with similarity scores
- Text snippets from documents
- Source metadata (document path, page number, chunk index)
- Relevance scores (0.0 to 1.0)

---

### 5. `list_profiles` - List Available Profiles

**Purpose**: Show all configured profiles in the system

**Example Questions:**

```
What profiles are available?
```

```
List all profiles
```

```
Show me the configured profiles
```

```
What document collections do you have?
```

**Expected Tool Call:**
```json
{}
```

**Expected Response:**
- Profile names (avi-cohen, informatica-cloud, dahua-camera)
- Document counts
- Embedding backend info
- Collection names

---

### 6. `plan_api_call` - AutoGen API Planner

**Purpose**: Use AutoGen to plan an API call based on documentation search

**Note**: Only available if `USE_AUTOGEN=1` is set

**Example Questions:**

**Informatica Cloud:**
```
How do I list all connections in Informatica Cloud?
```

```
Plan an API call to retrieve all mappings from informatica-cloud
```

```
What API call gets workflow details in informatica-cloud?
```

```
How do I fetch task logs using the informatica-cloud API?
```

**Dahua Camera:**
```
How do I enable WiFi using the dahua-camera API?
```

```
What API endpoint should I use to check camera status?
```

```
Plan an API call to configure network settings in dahua-camera
```

**Expected Tool Call:**
```json
{
  "q": "list all connections",
  "profile": "informatica-cloud"
}
```

**Expected Response:**
- HTTP method (GET, POST, PUT, DELETE)
- API endpoint path (e.g., `/api/v3/connections`)
- Required headers (Authorization, Content-Type)
- Query parameters or request body
- Evidence from documentation with scores
- Description of the API call

---

## Multi-Tool Workflows

**Search + List (GitHub):**
```
List all my repositories and tell me which ones are related to Python
```

**Search + Read (GitHub):**
```
Search for my MCP projects and show me the README from the first one
```

**Profile-based workflow (GitHub):**
```
Use the avi-cohen profile to list my repos, then summary the README from learning-mcp in 10 lines
```

**Document search + API planning (Informatica):**
```
Search informatica-cloud for connections, then plan an API call to list them
```

```
Find information about workflows in informatica-cloud, then give me the API endpoint
```

**Document search + API planning (Dahua):**
```
Search dahua-camera for WiFi configuration, then plan an API call to enable it
```

**Cross-profile comparison:**
```
Compare authentication methods between informatica-cloud and dahua-camera profiles
```

**Profile discovery + search:**
```
What profiles are available? Then search informatica-cloud for authentication
```

---

## Tips

1. **Profile names** are: `avi-cohen`, `informatica-cloud`, `dahua-camera`
2. **Default profile** for GitHub tools is `avi-cohen`
3. **Auto-scoping** works for search_github_repos - it adds `user:aviciot` automatically
4. **Be specific** about limits if you want fewer/more results (e.g., "top 10 results")
5. **Mention profile** explicitly if you want to test different profiles
6. **Document search** quality depends on ingested documents - check `/health` endpoint
7. **AutoGen planner** requires `USE_AUTOGEN=1` and profile with `autogen_hints` configured

---

## Testing Checklist

**GitHub Tools:**
- [ ] List your repositories (default profile)
- [ ] List repositories with explicit profile
- [ ] Search your repos (auto-scoping)
- [ ] Search other users' repos (override)
- [ ] Get a file from your repo
- [ ] Get a file from another repo

**Document Search Tools:**
- [ ] Search documents in informatica-cloud profile
- [ ] Search documents in dahua-camera profile
- [ ] Search documents in avi-cohen profile
- [ ] List all profiles
- [ ] Plan an API call with informatica-cloud (if AutoGen enabled)
- [ ] Plan an API call with dahua-camera (if AutoGen enabled)

**Multi-Tool Workflows:**
- [ ] GitHub search + file read workflow
- [ ] Document search + API planning workflow
- [ ] Cross-profile comparison

---

## Troubleshooting

**Tool not appearing?**
- Disconnect and reconnect in mcpjam
- Refresh the browser
- Restart the Docker container: `docker compose restart learning-mcp`

**Profile error?**
- Check profile name spelling (case-sensitive)
- Verify profile has `github.username` configured (for GitHub tools)
- Use `list_profiles` to see available profiles

**Empty search results?**
- Check if documents are ingested for that profile using `/health` endpoint
- Verify GitHub username exists
- Try with a different query or broader search terms
- Re-ingest documents if needed: `POST /ingest/jobs`

**AutoGen not working?**
- Check if `USE_AUTOGEN=1` in `.env` file
- Verify profile has `autogen_hints` configured in `learning.yaml`
- Check Docker logs: `docker compose logs -f learning-mcp`
- Test with simple queries first (e.g., "list connections")
