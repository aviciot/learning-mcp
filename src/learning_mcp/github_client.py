"""
GitHub integration for Learning MCP
Provides GitHub search and repository operations as MCP tools
"""

import os
import logging
from typing import List, Dict, Any, Optional
import httpx

log = logging.getLogger("learning_mcp.github")


class GitHubClient:
    """Simple GitHub API client"""
    
    def __init__(self, token: Optional[str] = None):
        self.token = token or os.getenv("GITHUB_PERSONAL_ACCESS_TOKEN")
        if not self.token:
            log.warning("No GitHub token provided - API calls will be rate-limited")
        
        self.base_url = "https://api.github.com"
        self.headers = {
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": "learning-mcp"
        }
        if self.token:
            self.headers["Authorization"] = f"token {self.token}"
    
    async def search_repositories(
        self,
        query: str,
        limit: int = 10,
        sort: str = "stars"
    ) -> List[Dict[str, Any]]:
        """
        Search GitHub repositories.
        
        Args:
            query: Search query (e.g., "RAG user:aviciot")
            limit: Max results to return
            sort: Sort by 'stars', 'forks', 'updated'
        
        Returns:
            List of repository objects with name, description, url, etc.
        """
        async with httpx.AsyncClient() as client:
            try:
                response = await client.get(
                    f"{self.base_url}/search/repositories",
                    headers=self.headers,
                    params={
                        "q": query,
                        "sort": sort,
                        "per_page": limit
                    },
                    timeout=10.0
                )
                response.raise_for_status()
                data = response.json()
                
                # Simplify response
                repos = []
                for item in data.get("items", [])[:limit]:
                    repos.append({
                        "name": item["name"],
                        "full_name": item["full_name"],
                        "description": item.get("description", ""),
                        "url": item["html_url"],
                        "stars": item["stargazers_count"],
                        "forks": item["forks_count"],
                        "language": item.get("language", ""),
                        "topics": item.get("topics", []),
                        "updated_at": item["updated_at"]
                    })
                
                return repos
            
            except Exception as e:
                log.error(f"GitHub API error: {e}")
                raise
    
    async def get_file_contents(
        self,
        owner: str,
        repo: str,
        path: str,
        ref: str = "main"
    ) -> Dict[str, Any]:
        """
        Get contents of a file from a repository.
        
        Args:
            owner: Repository owner (username or org)
            repo: Repository name
            path: Path to file (e.g., "README.md")
            ref: Branch/tag/commit (default: main)
        
        Returns:
            File content and metadata
        """
        async with httpx.AsyncClient() as client:
            try:
                response = await client.get(
                    f"{self.base_url}/repos/{owner}/{repo}/contents/{path}",
                    headers=self.headers,
                    params={"ref": ref},
                    timeout=10.0
                )
                response.raise_for_status()
                data = response.json()
                
                # Decode base64 content
                import base64
                content = base64.b64decode(data["content"]).decode("utf-8")
                
                return {
                    "name": data["name"],
                    "path": data["path"],
                    "size": data["size"],
                    "content": content,
                    "sha": data["sha"],
                    "url": data["html_url"]
                }
            
            except Exception as e:
                log.error(f"Error fetching file {owner}/{repo}/{path}: {e}")
                raise
    
    async def list_user_repos(
        self,
        username: str,
        limit: int = 100,
        type_filter: str = "all"
    ) -> List[Dict[str, Any]]:
        """
        List all repositories for a user.
        
        Args:
            username: GitHub username
            limit: Max repos to return
            type_filter: 'all', 'owner', 'member'
        
        Returns:
            List of repository objects
        """
        async with httpx.AsyncClient() as client:
            try:
                response = await client.get(
                    f"{self.base_url}/users/{username}/repos",
                    headers=self.headers,
                    params={
                        "type": type_filter,
                        "per_page": min(limit, 100),
                        "sort": "updated"
                    },
                    timeout=10.0
                )
                response.raise_for_status()
                data = response.json()
                
                repos = []
                for item in data[:limit]:
                    repos.append({
                        "name": item["name"],
                        "full_name": item["full_name"],
                        "description": item.get("description", ""),
                        "url": item["html_url"],
                        "stars": item["stargazers_count"],
                        "language": item.get("language", ""),
                        "topics": item.get("topics", []),
                        "private": item["private"],
                        "updated_at": item["updated_at"]
                    })
                
                return repos
            
            except Exception as e:
                log.error(f"Error listing repos for {username}: {e}")
                raise
