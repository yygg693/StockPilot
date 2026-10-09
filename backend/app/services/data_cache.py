"""SQLite-based persistent cache for K-line data with incremental update support."""
from __future__ import annotations

import json
from datetime import datetime, timedelta

from backend.app.core.logging import get_logger
from backend.app.db.session import get_db

logger = get_logger("data_cache")

# Cache freshness thresholds (how long cached data is considered fresh)
_FRESH_TTL = {
    "day": timedelta(hours=4),       # Daily K-line: 4 hours
    "week": timedelta(hours=12),     # Weekly: 12 hours
    "month": timedelta(hours=24),    # Monthly: 24 hours
}


async def get_cached_kline(code: str, period: str, count: int) -> list[dict] | None:
    """Return cached K-line data if fresh enough, else None."""
    db = await get_db()
    cursor = await db.execute(
        "SELECT data_json, updated_at FROM kline_cache WHERE code = ? AND period = ?",
        (code, period),
    )
    row = await cursor.fetchone()
    if not row:
        return None

    data_json, updated_at = row[0], row[1]
    ttl = _FRESH_TTL.get(period, timedelta(hours=4))
    try:
        last_update = datetime.fromisoformat(updated_at)
    except (ValueError, TypeError):
        return None

    if datetime.now() - last_update > ttl:
        logger.debug("kline_cache.stale", code=code, period=period)
        return None

    try:
        data = json.loads(data_json)
    except (json.JSONDecodeError, TypeError):
        return None

    # Return only the requested count (most recent)
    if len(data) > count:
        data = data[-count:]
    return data


async def save_kline(code: str, period: str, data: list[dict]) -> None:
    """Save K-line data to persistent cache (upsert)."""
    if not data:
        return
    db = await get_db()
    data_json = json.dumps(data, ensure_ascii=False)
    now = datetime.now().isoformat()
    await db.execute(
        """
        INSERT INTO kline_cache (code, period, data_json, updated_at, bar_count)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(code, period) DO UPDATE SET
            data_json = excluded.data_json,
            updated_at = excluded.updated_at,
            bar_count = excluded.bar_count
        """,
        (code, period, data_json, now, len(data)),
    )
    await db.commit()
    logger.debug("kline_cache.saved", code=code, period=period, count=len(data))


async def get_cached_quote(code: str) -> dict | None:
    """Return cached real-time quote (very short TTL, mainly for fallback)."""
    db = await get_db()
    cursor = await db.execute(
        "SELECT data_json, updated_at FROM quote_cache WHERE code = ?",
        (code,),
    )
    row = await cursor.fetchone()
    if not row:
        return None
    data_json, updated_at = row[0], row[1]
    try:
        last_update = datetime.fromisoformat(updated_at)
    except (ValueError, TypeError):
        return None
    # Quote cache: 3 seconds TTL
    if datetime.now() - last_update > timedelta(seconds=3):
        return None
    try:
        return json.loads(data_json)
    except (json.JSONDecodeError, TypeError):
        return None


async def save_quote(code: str, data: dict) -> None:
    """Save real-time quote to cache."""
    db = await get_db()
    data_json = json.dumps(data, ensure_ascii=False)
    now = datetime.now().isoformat()
    await db.execute(
        """
        INSERT INTO quote_cache (code, data_json, updated_at)
        VALUES (?, ?, ?)
        ON CONFLICT(code) DO UPDATE SET
            data_json = excluded.data_json,
            updated_at = excluded.updated_at
        """,
        (code, data_json, now),
    )
    await db.commit()


async def incremental_merge(existing: list[dict], new_data: list[dict]) -> list[dict]:
    """Merge new K-line data with existing cache, deduplicating by date."""
    if not new_data:
        return existing
    if not existing:
        return new_data
    merged = {bar["date"]: bar for bar in existing}
    for bar in new_data:
        merged[bar["date"]] = bar
    return sorted(merged.values(), key=lambda x: x["date"])
