"""Disk-backed TTL cache for expensive AI results.

Survives backend restarts so the first user after a restart doesn't wait
20s+ for signals/diagnosis to regenerate. Each key is a JSON file under
data/ai_cache/ containing {"ts": <epoch>, "value": <payload>}.
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from backend.app.core.config import DATA_DIR
from backend.app.core.logging import get_logger

logger = get_logger("disk_cache")

_CACHE_DIR = DATA_DIR / "ai_cache"


def _path(key: str) -> Path:
    safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in key)
    return _CACHE_DIR / f"{safe}.json"


def disk_get(key: str, ttl: float) -> Any | None:
    """Return cached value if present and younger than ttl seconds, else None."""
    try:
        p = _path(key)
        if not p.exists():
            return None
        with open(p, encoding="utf-8") as f:
            entry = json.load(f)
        if time.time() - entry.get("ts", 0) > ttl:
            return None
        return entry.get("value")
    except Exception as e:
        logger.warning("disk_cache.get_failed", key=key, error=str(e))
        return None


def disk_set(key: str, value: Any) -> None:
    """Persist value to disk (best-effort, never raises)."""
    try:
        _CACHE_DIR.mkdir(parents=True, exist_ok=True)
        tmp = _path(key).with_suffix(".tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump({"ts": time.time(), "value": value}, f, ensure_ascii=False)
        tmp.replace(_path(key))
    except Exception as e:
        logger.warning("disk_cache.set_failed", key=key, error=str(e))
