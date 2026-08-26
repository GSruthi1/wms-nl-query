"""
Centralized application settings.

Why this exists: scattering `os.environ.get(...)` calls across modules makes
it impossible to know what config the app actually needs, and it fails
silently (you get `None` instead of a startup error) when something is
missing. pydantic-settings gives us one source of truth, type validation,
and a loud failure at startup if a required value is missing/malformed.
"""
from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # --- Database ---
    # Privileged connection: runs migrations, writes audit_log rows.
    database_url: str = "postgresql+psycopg2://wms:wms@localhost:5432/wms"
    database_url_test: str = "postgresql+psycopg2://wms:wms@localhost:5432/wms_test"
    # Read-only connection: the ONLY role that ever executes LLM-generated
    # SQL. Granted SELECT on the WMS data tables and nothing else (not
    # audit_log) — see alembic/versions/0002_readonly_role.py. This is a
    # deliberate defense-in-depth layer: even if prompt/validator logic has
    # a bug, the DB-level grant is what actually stops a write or a read of
    # the audit trail.
    database_url_readonly: str = "postgresql+psycopg2://wms_readonly:wms_readonly@localhost:5432/wms"

    # --- LLM ---
    llm_provider: Literal["anthropic", "openai"] = "anthropic"
    anthropic_api_key: str | None = None
    openai_api_key: str | None = None
    llm_model_anthropic: str = "claude-sonnet-5"
    llm_model_openai: str = "gpt-4o"

    # --- Query safety ---
    sql_statement_timeout_ms: int = 5000
    sql_row_limit: int = 500

    # --- App ---
    environment: Literal["development", "test", "production"] = "development"
    log_level: str = "INFO"


@lru_cache
def get_settings() -> Settings:
    """Cached so we parse the environment once per process, not per request."""
    return Settings()
