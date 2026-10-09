"""Tencent finance data service (async httpx)."""
from __future__ import annotations

import re

import httpx

from backend.app.core.exceptions import DataSourceError
from backend.app.core.logging import get_logger

logger = get_logger("data_tencent")

_HEADERS = {"Referer": "https://finance.qq.com"}


async def fetch_quote_batch(client: httpx.AsyncClient, codes: list[str]) -> dict[str, dict]:
    """Fetch real-time quotes for a batch of codes (max ~60 per request)."""
    results: dict[str, dict] = {}
    # Tencent supports comma-separated codes
    for i in range(0, len(codes), 60):
        batch = codes[i:i + 60]
        url = f"https://qt.gtimg.cn/q={','.join(batch)}"
        try:
            r = await client.get(url, headers=_HEADERS, timeout=8.0)
            r.raise_for_status()
            results.update(_parse_quotes_text(r.text))
        except httpx.HTTPError as e:
            logger.warning("tencent.batch_failed", codes=batch[:3], error=str(e))
    return results


def _parse_quotes_text(text: str) -> dict[str, dict]:
    """Parse Tencent quote response text into structured dicts."""
    out: dict[str, dict] = {}
    for line in text.strip().split(";"):
        line = line.strip()
        if not line or "=" not in line:
            continue
        m = re.match(r'v_(\w+)="(.*)"', line)
        if not m:
            continue
        code = m.group(1)
        fields = m.group(2).split("~")
        if len(fields) < 50:
            continue
        try:
            out[code] = {
                "code": code,
                "name": fields[1],
                "price": _f(fields[3]),
                "prev_close": _f(fields[4]),
                "open": _f(fields[5]),
                "volume": _f(fields[6]),
                "high": _f(fields[33]),
                "low": _f(fields[34]),
                "change": _f(fields[31]),
                "change_pct": _f(fields[32]),
                "turnover": _f(fields[38]),
                "amount": _f(fields[37]),
                "pe": _f(fields[39]),
                "pe_dynamic": _f(fields[52]) if len(fields) > 52 else 0,
                "pb": _f(fields[46]),
                "market_cap": _f(fields[45]),
                "float_cap": _f(fields[44]) if len(fields) > 44 else 0,
                "amplitude": _f(fields[43]) if len(fields) > 43 else 0,
                "volume_ratio": _f(fields[49]) if len(fields) > 49 else 0,
                "avg_price": _f(fields[51]) if len(fields) > 51 else 0,
                "limit_up": _f(fields[47]) if len(fields) > 47 else 0,
                "limit_down": _f(fields[48]) if len(fields) > 48 else 0,
                "outer_vol": _f(fields[7]) if len(fields) > 7 else 0,
                "inner_vol": _f(fields[8]) if len(fields) > 8 else 0,
                "time": fields[30],
            }
        except (IndexError, ValueError):
            continue
    return out


async def parse_index_overview(client: httpx.AsyncClient, codes: list[str]) -> list[dict]:
    """Fetch and format major index data."""
    quotes = await fetch_quote_batch(client, codes)
    result = []
    for code in codes:
        q = quotes.get(code)
        if q:
            result.append(q)
    return result


async def fetch_kline(
    client: httpx.AsyncClient,
    code: str,
    period: str = "day",
    count: int = 120,
) -> list[dict]:
    """Fetch K-line data from Tencent.

    period: day/week/month
    Returns list of {date, open, close, high, low, volume}.
    """
    period_map = {"day": "day", "week": "week", "month": "month"}
    p = period_map.get(period, "day")
    url = (
        f"https://ifzq.gtimg.cn/appstock/app/fqkline/get"
        f"?param={code},{p},,,{count},qfq"
    )
    try:
        r = await client.get(url, headers=_HEADERS, timeout=10.0)
        r.raise_for_status()
        data = r.json()
    except Exception as e:
        raise DataSourceError(f"K-line fetch failed for {code}", detail=str(e)) from e

    # Navigate response structure
    try:
        stock_data = data["data"][code]
        # Try qfq first, then raw period key
        klines = stock_data.get(f"qfq{p}") or stock_data.get(p, [])
    except (KeyError, TypeError):
        return []

    result = []
    for k in klines:
        if len(k) < 6:
            continue
        result.append({
            "date": k[0],
            "open": _f(k[1]),
            "close": _f(k[2]),
            "high": _f(k[3]),
            "low": _f(k[4]),
            "volume": _f(k[5]),
        })
    return result


def _f(s: str) -> float:
    try:
        return float(s)
    except (ValueError, TypeError):
        return 0.0
