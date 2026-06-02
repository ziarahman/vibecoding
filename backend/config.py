"""
config.py
=========
Centralized, environment-driven configuration.

Everything that toggles behaviour between "local Ollama dev" and
"cloud-LLM production" funnels through here so the rest of the codebase never
reads `os.environ` directly.
"""

from __future__ import annotations

from functools import lru_cache
from typing import List, Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    # --- App ---
    app_name: str = "IPO Signal Intelligence"
    environment: str = "development"

    # --- Database ---
    # Default: file-backed SQLite next to the backend. Swap for a Postgres
    # URL (postgresql+psycopg://...) without touching application code.
    database_url: str = "sqlite:///./ipo_signals.db"

    # --- CORS ---
    # Comma-separated list of allowed frontend origins.
    cors_origins: str = "http://localhost:3000,http://127.0.0.1:3000"

    # --- LLM provider switch ---
    # One of: "ollama", "openai", "anthropic".
    llm_provider: str = "ollama"

    # Ollama (local)
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "llama3.1"

    # OpenAI (cloud)
    openai_api_key: Optional[str] = None
    openai_model: str = "gpt-4o-mini"

    # Anthropic (cloud)
    anthropic_api_key: Optional[str] = None
    anthropic_model: str = "claude-sonnet-4-6"

    llm_temperature: float = 0.0

    # --- Discovery ---
    tavily_api_key: Optional[str] = None
    # Comma-separated RSS feeds scanned by the Discovery node.
    # SEC EDGAR atom feed + fallback Yahoo Finance IPO news feed (Nasdaq RSS is unreliable).
    rss_feeds: str = (
        "https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&type=S-1&dateb=&owner=include&count=40&search_text=&output=atom,"
        "https://feeds.finance.yahoo.com/rss/2.0/headline?s=ipo&region=US&lang=en-US"
    )
    discovery_max_documents: int = 12
    rss_timeout_seconds: float = 20.0
    # SEC EDGAR requires User-Agent in "Company Name email@domain.com" format.
    # Override HTTP_USER_AGENT in .env with your actual contact details.
    http_user_agent: str = "ipo-signal-intel contact@example.com"

    # --- SEC EDGAR ---
    sec_edgar_base: str = "https://efts.sec.gov/LATEST/search-index"
    sec_fulltext_search: str = "https://efts.sec.gov/LATEST/search-index?q="

    @property
    def cors_origin_list(self) -> List[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def rss_feed_list(self) -> List[str]:
        return [f.strip() for f in self.rss_feeds.split(",") if f.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
