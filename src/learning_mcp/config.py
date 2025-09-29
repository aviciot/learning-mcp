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

settings = Settings()
