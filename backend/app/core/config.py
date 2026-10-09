"""Pydantic Settings: env vars > data/ai_config.json > config.yaml > defaults."""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

import yaml
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT_DIR = Path(__file__).resolve().parents[3]  # D:/StockPilot
CONFIG_PATH = ROOT_DIR / "config.yaml"
DATA_DIR = ROOT_DIR / "data"
FRONTEND_DIR = ROOT_DIR / "frontend-v2" / "dist"
DB_PATH = DATA_DIR / "stockpilot_v2.db"
AI_CONFIG_PATH = DATA_DIR / "ai_config.json"


def _load_yaml() -> dict:
    if CONFIG_PATH.exists():
        with open(CONFIG_PATH, encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    return {}


def _load_ai_json() -> dict:
    """Load user-saved AI config from data/ai_config.json (written by the
    settings page via POST /api/config/ai/save). Returns {} if the file is
    missing or unreadable so startup never fails because of a bad config.

    The api_key field is intentionally discarded: secrets must come from the
    STOCKPILOT_AI_API_KEY environment variable or runtime memory, never from disk."""
    if AI_CONFIG_PATH.exists():
        try:
            with open(AI_CONFIG_PATH, encoding="utf-8") as f:
                data = json.load(f) or {}
            data.pop("api_key", None)
            return data
        except Exception:
            return {}
    return {}


_yaml = _load_yaml()
_ai_yaml = _yaml.get("ai", {})
_ai_json = _load_ai_json()
_server_yaml = _yaml.get("server", {})
_cache_yaml = _yaml.get("cache", {})
_disc_yaml = _yaml.get("discipline", {})
_security_yaml = _yaml.get("security", {})


def _ai_default(key: str, fallback):
    """Prefer the user-saved JSON value, then config.yaml, then the fallback."""
    if key in _ai_json and _ai_json[key] is not None:
        return _ai_json[key]
    return _ai_yaml.get(key, fallback)


class AISettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="STOCKPILOT_AI_")

    api_key: str = Field(default=_ai_default("api_key", ""))
    base_url: str = Field(default=_ai_default("base_url", "https://api.deepseek.com"))
    model: str = Field(default=_ai_default("model", "deepseek-chat"))
    enabled: bool = Field(default=_ai_default("enabled", True))

    @property
    def configured(self) -> bool:
        return bool(self.api_key.strip())


class ServerSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="STOCKPILOT_SERVER_")

    host: str = Field(default=_server_yaml.get("host", "127.0.0.1"))
    port: int = Field(default=_server_yaml.get("port", 8000))
    api_key: str = Field(default="")  # STOCKPILOT_SERVER_API_KEY


class CacheSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="STOCKPILOT_CACHE_")

    quote_ttl: int = Field(default=_cache_yaml.get("quote_ttl", 3))       # seconds
    kline_ttl: int = Field(default=_cache_yaml.get("kline_ttl", 30))       # minutes
    news_ttl: int = Field(default=_cache_yaml.get("news_ttl", 30))         # minutes
    snapshot_ttl: int = Field(default=_cache_yaml.get("snapshot_ttl", 30)) # minutes


class DisciplineSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="STOCKPILOT_DISC_")

    chase_high_pct: float = Field(default=_disc_yaml.get("chase_high_pct", 10))
    stop_loss_pct: float = Field(default=_disc_yaml.get("stop_loss_pct", 8))


class SecuritySettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="STOCKPILOT_SECURITY_")

    cors_origins: list[str] = Field(
        default_factory=lambda: _security_yaml.get("cors_origins", [
            "http://localhost:5173",
            "http://127.0.0.1:5173",
        ])
    )
    rate_limit_per_minute: int = Field(default=_security_yaml.get("rate_limit_per_minute", 60))
    ai_rate_limit_per_minute: int = Field(default=_security_yaml.get("ai_rate_limit_per_minute", 20))
    jwt_secret: str = Field(default=_security_yaml.get("jwt_secret", "stockpilot-jwt-secret-change-me-in-production-2026"))
    jwt_expire_hours: int = Field(default=_security_yaml.get("jwt_expire_hours", 24))
    auth_enabled: bool = Field(default=_security_yaml.get("auth_enabled", False))


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="STOCKPILOT_")

    debug: bool = Field(default=False)
    ai: AISettings = Field(default_factory=AISettings)
    server: ServerSettings = Field(default_factory=ServerSettings)
    cache: CacheSettings = Field(default_factory=CacheSettings)
    discipline: DisciplineSettings = Field(default_factory=DisciplineSettings)
    security: SecuritySettings = Field(default_factory=SecuritySettings)


def save_ai_config_to_disk(api_key: str, base_url: str, model: str, enabled: bool = True) -> dict:
    """Persist AI config to data/ai_config.json so it survives backend restarts.

    The API key is NEVER written to disk: it is kept in memory (runtime settings)
    or provided via the STOCKPILOT_AI_API_KEY environment variable. Only
    non-secret fields are persisted, so no plaintext secret is left on disk."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    payload = {
        "base_url": base_url,
        "model": model,
        "enabled": enabled,
    }
    with open(AI_CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    return payload


@lru_cache
def get_settings() -> Settings:
    return Settings()
