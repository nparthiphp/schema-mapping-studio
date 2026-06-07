from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", case_sensitive=False)

    # Service
    app_name: str = "schema-mapping-studio"
    app_version: str = "1.0.0"
    env: str = "development"
    port: int = 8080
    log_level: str = "INFO"

    # Security
    api_key: str = "changeme-in-production"
    payload_max_bytes: int = 51_200        # 50 KB hard limit

    # Anthropic
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-sonnet-4-20250514"
    anthropic_max_tokens: int = 1200
    anthropic_timeout: int = 30
    llm_max_retries: int = 3

    # Database
    database_url: str = "sqlite+aiosqlite:///./data/sms.db"

    # JSONata runner (Node.js subprocess path)
    node_binary: str = "node"
    jsonata_script: str = "scripts/jsonata_runner.js"
    jsonata_timeout: int = 10


@lru_cache
def get_settings() -> Settings:
    return Settings()
