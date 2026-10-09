"""Quote routes: index overview, stock detail, kline, search, news, breadth."""
from __future__ import annotations

import re

from fastapi import APIRouter, Depends, Query

from backend.app.core.cache import TTLCache
from backend.app.core.config import get_settings
from backend.app.core.exceptions import NotFoundError
from backend.app.core.http_client import get_http_client
from backend.app.core.logging import get_logger
from backend.app.deps import get_cache
from backend.app.services.data_source import get_kline, get_quote
from backend.app.services.data_tencent import parse_index_overview

logger = get_logger("quote")
router = APIRouter()

_INDEX_CODES = ["sh000001", "sz399001", "sz399006"]


@router.get("/index")
async def index_overview(cache: TTLCache = Depends(get_cache)):
    cached = await cache.get("index_overview")
    if cached:
        return {"data": cached}
    client = get_http_client()
    data = await parse_index_overview(client, _INDEX_CODES)
    await cache.set("index_overview", data, ttl=3)
    return {"data": data}


@router.get("/quote")
async def quote(code: str = Query(..., description="e.g. sh600519"), cache: TTLCache = Depends(get_cache)):
    cache_key = f"quote:{code}"
    cached = await cache.get(cache_key)
    if cached:
        return {"data": cached}
    client = get_http_client()
    result = await get_quote(client, code)
    if not result:
        raise NotFoundError(f"Quote not found for {code}")
    settings = get_settings()
    await cache.set(cache_key, result, ttl=settings.cache.quote_ttl)
    return {"data": result}


@router.get("/kline")
async def kline(
    code: str = Query(...),
    period: str = Query("day", pattern="^(day|week|month)$"),
    count: int = Query(120, ge=1, le=500),
    cache: TTLCache = Depends(get_cache),
):
    cache_key = f"kline:{code}:{period}:{count}"
    cached = await cache.get(cache_key)
    if cached:
        return {"data": cached}
    client = get_http_client()
    settings = get_settings()
    data = await get_kline(client, code, period=period, count=count)
    await cache.set(cache_key, data, ttl=settings.cache.kline_ttl * 60)
    return {"data": data}


@router.get("/search")
async def search(q: str = Query(..., min_length=1), cache: TTLCache = Depends(get_cache)):
    """Search stocks by code or name prefix."""
    cache_key = f"search:{q}"
    cached = await cache.get(cache_key)
    if cached:
        return {"data": cached}

    client = get_http_client()
    # Use Tencent smart search API
    try:
        r = await client.get(
            "https://smartbox.gtimg.cn/s3/",
            params={"v": "2", "q": q, "t": "all", "c": "1"},
            headers={"Referer": "https://finance.qq.com"},
            timeout=5.0,
        )
        # smartbox returns GBK-encoded text
        text = r.content.decode('gbk', errors='replace')
        # Parse: v_hint="code~name~market~...^..."
        results = []
        match = re.search(r'v_hint="(.*)"', text)
        if match and match.group(1):
            items = match.group(1).split("^")
            for item in items[:10]:
                parts = item.split("~")
                if len(parts) >= 3:
                    # Tencent smartbox format: market~code~name~...
                    market = parts[0]  # "sh" or "sz"
                    raw_code = parts[1]  # "600519"
                    name = parts[2]  # "贵州茅台"
                    if market in ("sh", "sz"):
                        full_code = f"{market}{raw_code}"
                    elif raw_code.startswith(("6", "5")):
                        full_code = f"sh{raw_code}"
                    else:
                        full_code = f"sz{raw_code}"
                    results.append({"code": full_code, "name": name, "market": market})
    except Exception as e:
        logger.warning("search.failed", query=q, error=str(e))
        results = []

    await cache.set(cache_key, results, ttl=300)
    return {"data": results}


# Large pool of liquid stocks for breadth calculation (same as sector.py _MOVER_POOL)
_BREADTH_POOL = (
    "sh600519,sh601318,sz000858,sh600036,sz300750,sh601012,sz002594,sh600900,"
    "sz000001,sh601899,sh600030,sz002475,sh600276,sz300059,sh601888,sz000333,"
    "sh600809,sz002304,sh601166,sh600887,sh601398,sh600000,sz000002,sh601668,"
    "sh600585,sz002415,sh601601,sh600104,sz000568,sh601088,sh600309,sz002714,"
    "sh600690,sz000725,sh601225,sz300124,sh600031,sz002352,sh601633,sz000651,"
    "sh600048,sz002027,sh601857,sh600050,sz300760,sh601919,sz002230,sh600588,"
    "sz000063,sh601006,sh600150,sz002049,sh601766,sz300015,sh600436,sz002142,"
    "sh601390,sh600089,sz000977,sh601138,sz300122,sh600703,sz002460,sh601688"
)


@router.get("/breadth")
async def breadth(cache: TTLCache = Depends(get_cache)):
    """Market breadth: up/down/flat counts from a liquid stock pool."""
    cached = await cache.get("market_breadth")
    if cached:
        return {"data": cached}

    client = get_http_client()
    up = 0
    down = 0
    flat = 0
    limit_up = 0
    limit_down = 0
    total_pct = 0.0
    total_amount = 0.0
    count = 0

    try:
        r = await client.get(
            f"https://qt.gtimg.cn/q={_BREADTH_POOL}",
            headers={"Referer": "https://finance.qq.com"},
            timeout=10.0,
        )
        for line in r.text.strip().split(";"):
            line = line.strip()
            if not line or "=" not in line:
                continue
            m = re.match(r'v_(\w+)="(.*)"', line)
            if not m:
                continue
            fields = m.group(2).split("~")
            if len(fields) < 38:
                continue
            try:
                pct = float(fields[32]) if fields[32] else 0.0
                amount = float(fields[37]) if len(fields) > 37 and fields[37] else 0.0
            except (ValueError, IndexError):
                continue

            count += 1
            total_pct += pct
            total_amount += amount

            if pct > 0.01:
                up += 1
                if pct >= 9.9:
                    limit_up += 1
            elif pct < -0.01:
                down += 1
                if pct <= -9.9:
                    limit_down += 1
            else:
                flat += 1
    except Exception as e:
        logger.warning("breadth.fetch_failed", error=str(e))

    total = up + down + flat
    avg_pct = round(total_pct / count, 2) if count > 0 else 0.0
    up_pct = round(up / total * 100, 1) if total > 0 else 0.0
    down_pct = round(down / total * 100, 1) if total > 0 else 0.0
    flat_pct = round(flat / total * 100, 1) if total > 0 else 0.0

    data = {
        "up": up,
        "down": down,
        "flat": flat,
        "limit_up": limit_up,
        "limit_down": limit_down,
        "avg_pct": avg_pct,
        "up_pct": up_pct,
        "down_pct": down_pct,
        "flat_pct": flat_pct,
        "up_count": up,
        "down_count": down,
        "flat_count": flat,
        "total_amount": round(total_amount, 0),
        "north_flow": 0,
    }

    await cache.set("market_breadth", data, ttl=30)
    return {"data": data}

@router.get("/kline/minute")
async def kline_minute(
    code: str = Query(...),
    period: str = Query("m5", description="m1/m5/m15/m30/m60"),
    count: int = Query(120, ge=10, le=640),
    cache: TTLCache = Depends(get_cache),
):
    """Get minute-level K-line data from Tencent."""
    cache_key = f"kline_min:{code}:{period}:{count}"
    cached = await cache.get(cache_key)
    if cached:
        return {"data": cached}

    client = get_http_client()
    klines = []
    try:
        r = await client.get(
            "https://ifzq.gtimg.cn/appstock/app/kline/mkline",
            params={"param": f"{code},{period},,{count}"},
            timeout=10.0,
        )
        data = r.json()
        # Response: {"code":0, "data":{"sh600519":{"m5":[[date,open,close,high,low,volume],...]}}}
        stock_data = data.get("data", {}).get(code, {})
        raw = stock_data.get(period, stock_data.get(f"qfq{period}", []))
        for item in raw:
            if len(item) >= 6:
                klines.append({
                    "date": item[0],
                    "open": float(item[1]),
                    "close": float(item[2]),
                    "high": float(item[3]),
                    "low": float(item[4]),
                    "volume": float(item[5]),
                })
    except Exception as e:
        logger.warning("kline_minute.failed", code=code, error=str(e))

    await cache.set(cache_key, klines, ttl=30)
    return {"data": klines}


@router.get("/realtime")
async def realtime_minute(
    code: str = Query(...),
    cache: TTLCache = Depends(get_cache),
):
    """Get today's real-time minute-by-minute data (分时图)."""
    cache_key = f"realtime:{code}"
    cached = await cache.get(cache_key)
    if cached:
        return {"data": cached}

    client = get_http_client()
    result = {"code": code, "prev_close": 0, "minutes": []}
    try:
        r = await client.get(
            "https://ifzq.gtimg.cn/appstock/app/minute/query",
            params={"code": code},
            timeout=10.0,
        )
        data = r.json()
        stock_data = data.get("data", {}).get(code, {}).get("data", {})
        result["prev_close"] = float(stock_data.get("pre_close", 0) or 0)
        raw_minutes = stock_data.get("data", [])
        # Format: "0930 12.50 1234" -> time, price, volume
        for line in raw_minutes:
            parts = line.split(" ")
            if len(parts) >= 3:
                result["minutes"].append({
                    "time": parts[0],
                    "price": float(parts[1]),
                    "volume": float(parts[2]),
                })
    except Exception as e:
        logger.warning("realtime.failed", code=code, error=str(e))

    await cache.set(cache_key, result, ttl=15)
    return {"data": result}
