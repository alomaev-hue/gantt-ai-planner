import os
from functools import lru_cache
from typing import Literal

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import URL


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    db_host: str = "localhost"
    db_port: int = 55432
    db_name: str = "planner"
    db_user: str = "planner_app"
    db_password: SecretStr = SecretStr("planner")
    database_url: str | None = None

    public_origin: str = "http://localhost:8000"
    cookie_secure: bool = False

    llm_provider: Literal["anthropic", "fake"] = "fake"
    llm_model: str = "claude-sonnet-5"
    anthropic_api_key: SecretStr | None = None
    llm_max_tokens: int = 4096

    chat_limit_per_hour: int = 30
    chat_limit_per_day: int = 500
    # Per client IP (in-memory, sliding hour): new sessions and chat messages across sessions.
    session_limit_per_ip_hour: int = 20
    chat_limit_per_ip_hour: int = 60
    # Take the client IP from the last X-Forwarded-For hop (the one our reverse proxy set).
    # Only turn on when every request reaches the app through that proxy (production: Caddy
    # on the internal network); otherwise any client could pick its own "IP".
    trust_proxy: bool = False
    max_upload_mb: int = 2
    session_ttl_days: int = 14
    max_versions: int = 50
    static_dir: str | None = None
    log_level: str = "INFO"

    @property
    def sqlalchemy_url(self) -> str:
        if self.database_url:
            return self.database_url
        return URL.create(
            "postgresql+asyncpg",
            username=self.db_user,
            password=self.db_password.get_secret_value(),
            host=self.db_host,
            port=self.db_port,
            database=self.db_name,
        ).render_as_string(hide_password=False)


@lru_cache
def get_settings() -> Settings:
    return Settings(_secrets_dir=os.environ.get("SECRETS_DIR") or None)
