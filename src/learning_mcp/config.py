#path: src/learning_mcp/config.py

from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Any
import yaml
from pathlib import Path

class Settings(BaseSettings):
    ENV: str = "dev"
    PORT: int = 8013
    PROFILES_PATH: str = "/app/config/learning.yaml"
    VECTOR_DB_URL: str | None = None

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    def load_profiles(self) -> dict[str, Any]:
        p = Path(self.PROFILES_PATH)
        if not p.exists():
            return {"version": 1, "profiles": []}
        with p.open("r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {"version": 1, "profiles": []}
    
    def get_enabled_mcp_tools(self) -> list[str]:
        """
        Get list of enabled MCP tools from configuration.
        
        Returns:
            List of enabled tool names. Defaults to all tools if not configured.
        """
        config = self.load_profiles()
        mcp_config = config.get("mcp", {})
        return mcp_config.get("enabled_tools", [
            "search_docs",
            "list_profiles",
            "list_user_github_repos",
            "search_github_repos",
            "get_github_file",
            "plan_api_call"
        ])

settings = Settings()


def get_config() -> dict:
    """Get the full configuration dict from learning.yaml."""
    return settings.load_profiles()


def get_profile(name: str) -> dict:
    """
    Get a specific profile by name from learning.yaml.
    
    Args:
        name: Profile name
        
    Returns:
        Profile configuration dict
        
    Raises:
        KeyError: If profile not found
    """
    config = get_config()
    profiles_list = config.get("profiles", [])
    
    # Profiles are stored as a list, not a dict
    for profile in profiles_list:
        if profile.get("name") == name:
            return profile
    
    raise KeyError(f"Profile '{name}' not found in learning.yaml")

