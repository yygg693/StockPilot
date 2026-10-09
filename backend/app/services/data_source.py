"""Unified data access layer with persistent cache + multi-source fallback + validation."""
from __future__ import annotations

import httpx

from backend.app.core.logging import get_logger
from backend.app.services.data_cache import (
    get_cached_kline,
    get_cached_quote,
    incremental_merge,
    save_kline,
    save_quote,
)
from backend.app.services.data_eastmoney import fetch_kline as em_kline
from backend.app.services.data_eastmoney import fetch_quote_batch as em_quotes
from backend.app.services.data_tencent import fetch_kline as tencent_kline
from backend.app.services.data_tencent import fetch_quote_batch as tencent_quotes

logger = get_logger("data_source")


def validate_kline(data: list[dict]) -> list[dict]:
    """Validate and filter K-line data for quality.

    Checks:
    - price > 0
    - high >= low
    - high >= open, close
    - low <= open, close
    - volume >= 0
    """
    clean = []
    for bar in data:
        try:
            o, c, h, lo, v = bar["open"], bar["close"], bar["high"], bar["low"], bar["volume"]
            # Skip bars with zero or negative prices
            if o <= 0 or c <= 0 or h <= 0 or lo <= 0:
                continue
            # Skip bars where high < low (data error)
            if h < lo:
                continue
            # Skip bars with negative volume
            if v < 0:
                continue
            # Auto-fix: ensure high is the max and low is the min
            bar["high"] = max(h, o, c)
            bar["low"] = min(lo, o, c)
            clean.append(bar)
        except (KeyError, TypeError, ValueError):
            continue
    return clean


def validate_quote(quote: dict) -> bool:
    """Validate a single quote dict. Returns True if valid."""
    try:
        price = quote.get("price", 0)
        if price <= 0:
            return False
        # Check for obvious errors (price > 100000 is suspicious for A-shares)
        return price <= 100000
    except (TypeError, ValueError):
        return False


async def get_kline(
    client: httpx.AsyncClient,
    code: str,
    period: str = "day",
    count: int = 120,
) -> list[dict]:
    """Get K-line data with cache + multi-source fallback.

    Flow: persistent cache → Tencent → East Money → stale cache fallback.
    """
    # 1. Try persistent cache
    cached = await get_cached_kline(code, period, count)
    if cached and len(cached) >= count:
        return cached

    # 2. Try Tencent (primary source)
    data = []
    try:
        data = await tencent_kline(client, code, period=period, count=count)
        data = validate_kline(data)
        if data:
            logger.debug("kline.source", code=code, source="tencent", count=len(data))
    except Exception as e:
        logger.warning("kline.tencent_failed", code=code, error=str(e))

    # 3. Fallback to East Money
    if not data:
        try:
            data = await em_kline(client, code, period=period, count=count)
            data = validate_kline(data)
            if data:
                logger.debug("kline.source", code=code, source="eastmoney", count=len(data))
        except Exception as e:
            logger.warning("kline.eastmoney_failed", code=code, error=str(e))

    # 4. Fallback to stale cache (better than nothing)
    if not data and cached:
        logger.info("kline.stale_fallback", code=code, period=period)
        return cached

    # 5. Merge with existing cache and save
    if data:
        if cached:
            data = await incremental_merge(cached, data)
        # Trim to reasonable size (keep last 500 bars)
        if len(data) > 500:
            data = data[-500:]
        await save_kline(code, period, data)
        # Return only requested count
        if len(data) > count:
            data = data[-count:]

    return data


async def get_quote(
    client: httpx.AsyncClient,
    code: str,
) -> dict | None:
    """Get real-time quote with multi-source fallback.

    Flow: memory cache (handled by caller) → Tencent → East Money → persistent cache.
    """
    # 1. Try Tencent
    try:
        result = await tencent_quotes(client, [code])
        if code in result and validate_quote(result[code]):
            await save_quote(code, result[code])
            return result[code]
    except Exception as e:
        logger.warning("quote.tencent_failed", code=code, error=str(e))

    # 2. Fallback to East Money
    try:
        result = await em_quotes(client, [code])
        if code in result and validate_quote(result[code]):
            await save_quote(code, result[code])
            return result[code]
    except Exception as e:
        logger.warning("quote.eastmoney_failed", code=code, error=str(e))

    # 3. Fallback to persistent cache (may be slightly stale)
    cached = await get_cached_quote(code)
    if cached:
        logger.info("quote.cache_fallback", code=code)
        return cached

    return None


async def get_quote_batch(
    client: httpx.AsyncClient,
    codes: list[str],
) -> dict[str, dict]:
    """Get batch quotes with fallback."""
    # 1. Try Tencent
    try:
        result = await tencent_quotes(client, codes)
        # Validate each quote
        valid = {k: v for k, v in result.items() if validate_quote(v)}
        if valid:
            for code, quote in valid.items():
                await save_quote(code, quote)
            return valid
    except Exception as e:
        logger.warning("quote_batch.tencent_failed", error=str(e))

    # 2. Fallback to East Money
    try:
        result = await em_quotes(client, codes)
        valid = {k: v for k, v in result.items() if validate_quote(v)}
        if valid:
            return valid
    except Exception as e:
        logger.warning("quote_batch.eastmoney_failed", error=str(e))

    return {}
