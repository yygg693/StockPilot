"""Pydantic Settings: UI-saved file > env vars > config.yaml > defaults.

AI settings are resolved by ``_build_ai_settings`` with the priority:
    1. data/ai_config.json  (saved from the Settings page — wins)
    2. STOCKPILOT_AI_* env vars
    3. config.yaml ``ai:`` block
    4. built-in defaults
This guarantees a key configured in the UI survives restarts and isn't
silently overridden by an env var."""
from __future__ import annotations

import base64
import hashlib
import json
import os
import sys
from functools import lru_cache
from pathlib import Path

import yaml
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


def _base_dir() -> Path:
    """Project base directory.

    - Dev: three levels up from this file -> D:/StockPilot.
    - Frozen (PyInstaller --onedir): bundled assets (config.yaml, backend,
      frontend-v2/dist) live under ``sys._MEIPASS`` (the "_internal" subdir in
      PyInstaller 6+). Fall back to the executable directory for older layouts.
    """
    if getattr(sys, "frozen", False):
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            return Path(meipass)
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[3]


def _data_dir() -> Path:
    """Writable data directory.

    A frozen desktop build must not write into its install directory
    (often read-only, e.g. Program Files), so we use %APPDATA%/StockPilot/data
    when available. If APPDATA is missing (portable/clean environments), fall
    back to the user's home directory instead of the read-only bundled
    directory, so the app never fails to persist data. In dev we keep ./data.
    """
    if getattr(sys, "frozen", False):
        appdata = os.environ.get("APPDATA")
        if appdata:
            return Path(appdata) / "StockPilot" / "data"
        try:
            return Path.home() / "StockPilot" / "data"
        except Exception:
            return Path(sys.executable).resolve().parent.parent / "StockPilotData"
    return _base_dir() / "data"


# Kept as ROOT_DIR for any legacy references; equals _base_dir() in dev.
ROOT_DIR = _base_dir()
BASE_DIR = _base_dir()
CONFIG_PATH = BASE_DIR / "config.yaml"
DATA_DIR = _data_dir()
FRONTEND_DIR = BASE_DIR / "frontend-v2" / "dist"
DB_PATH = DATA_DIR / "stockpilot_v2.db"
AI_CONFIG_PATH = DATA_DIR / "ai_config.json"


def _load_yaml() -> dict:
    if CONFIG_PATH.exists():
        with open(CONFIG_PATH, encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    return {}


def _device_key_seed() -> str:
    """Cheap device-bound seed used only to obfuscate the AI key at rest.

    This is NOT a security boundary: it just avoids leaving the raw sk-... key
    in plaintext on disk for a local single-user desktop app. The key is bound
    to the machine so it can't simply be copied to another PC."""
    parts = [
        os.environ.get("COMPUTERNAME", ""),
        os.environ.get("USERNAME", ""),
        os.environ.get("USERDOMAIN", ""),
        "StockPilot::ai-secret::v1",
    ]
    return "|".join(parts)


def _encrypt_secret(plain: str) -> str:
    if not plain:
        return ""
    key = hashlib.sha256(_device_key_seed().encode("utf-8")).digest()
    raw = plain.encode("utf-8")
    cipher = bytes(b ^ key[i % len(key)] for i, b in enumerate(raw))
    return "enc:" + base64.b64encode(cipher).decode("ascii")


def _decrypt_secret(token: str) -> str:
    if not token:
        return ""
    if not token.startswith("enc:"):
        return token  # tolerate legacy plaintext entries
    try:
        key = hashlib.sha256(_device_key_seed().encode("utf-8")).digest()
        cipher = base64.b64decode(token[len("enc:"):])
        raw = bytes(b ^ key[i % len(key)] for i, b in enumerate(cipher))
        return raw.decode("utf-8")
    except Exception:
        return ""


def _load_ai_json() -> dict:
    """Load user-saved AI config from data/ai_config.json (written by the
    settings page via POST /api/config/ai/save). Returns {} if the file is
    missing or unreadable so startup never fails because of a bad config.

    The saved api_key is encrypted at rest and decrypted here, so a key
    configured in Settings survives backend restarts on the same machine."""
    if AI_CONFIG_PATH.exists():
        try:
            with open(AI_CONFIG_PATH, encoding="utf-8") as f:
                data = json.load(f) or {}
            if data.get("api_key"):
                data["api_key"] = _decrypt_secret(data["api_key"])
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


class AISettings(BaseModel):
    api_key: str = ""
    base_url: str = "https://api.deepseek.com"
    # deepseek-chat / deepseek-reasoner were retired on 2026-07-24; the current
    # DeepSeek API models are deepseek-v4-flash (general) and deepseek-v4-pro
    # (reasoning). Default to the recommended general model.
    model: str = "deepseek-v4-flash"
    enabled: bool = True

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
    rate_limit_per_minute: int = Field(default=_security_yaml.get("rate_limit_per_minute", 120))
    ai_rate_limit_per_minute: int = Field(default=_security_yaml.get("ai_rate_limit_per_minute", 60))
    # No hardcoded secret. Production deployments MUST set a strong secret via
    # the STOCKPILOT_SECURITY_JWT_SECRET env var (>=32 chars); otherwise the
    # key is empty and auth must stay disabled (local desktop use).
    jwt_secret: str = Field(default=_security_yaml.get("jwt_secret", ""))
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

    The api_key is encrypted at rest (device-bound) rather than stored in
    plaintext, so a key configured from the Settings page is reusable across
    relaunches of the desktop app without re-entering it."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    payload = {
        "api_key": _encrypt_secret(api_key),
        "base_url": base_url,
        "model": model,
        "enabled": enabled,
    }
    with open(AI_CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    return payload


def _build_ai_settings() -> AISettings:
    """Resolve AI settings with priority: UI-saved file > env vars > defaults.

    A key configured from the Settings page (persisted to ai_config.json) must
    win over STOCKPILOT_AI_* env vars, otherwise the UI config silently loses
    to the env var after every restart and AI appears "not configurable"."""
    env_key = os.environ.get("STOCKPILOT_AI_API_KEY", "")
    env_base = os.environ.get("STOCKPILOT_AI_BASE_URL", "")
    env_model = os.environ.get("STOCKPILOT_AI_MODEL", "")
    env_enabled = os.environ.get("STOCKPILOT_AI_ENABLED", None)

    file_key = _ai_json.get("api_key") or ""
    file_base = _ai_json.get("base_url") or ""
    file_model = _ai_json.get("model") or ""
    file_enabled = _ai_json.get("enabled", None)

    if file_enabled is None:
        enabled = env_enabled.lower() not in ("0", "false", "") if env_enabled else True
    else:
        enabled = bool(file_enabled)

    return AISettings(
        api_key=file_key or env_key,
        base_url=file_base or env_base or "https://api.deepseek.com",
        model=file_model or env_model or "deepseek-v4-flash",
        enabled=enabled,
    )


@lru_cache
def get_settings() -> Settings:
    return Settings(ai=_build_ai_settings())
