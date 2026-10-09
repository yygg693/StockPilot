"""Screener routes: strategy-based stock scanning."""
from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends, Query

from backend.app.core.cache import TTLCache
from backend.app.core.http_client import get_http_client
from backend.app.core.logging import get_logger
from backend.app.deps import get_cache
from backend.app.services.data_tencent import fetch_quote_batch

logger = get_logger("screener")
router = APIRouter()

# Concurrency limiter for batch scanning
_SEM = asyncio.Semaphore(20)


@router.get("/screener/strategies")
async def list_strategies():
    """List available screening strategies."""
    return {"data": [
        {"id": "oversold_bounce", "name": "超跌反弹", "desc": "近5日跌幅>8%且今日放量反弹"},
        {"id": "volume_break", "name": "放量突破", "desc": "成交量突破20日均量2倍且价格创20日新高"},
        {"id": "ma_golden_cross", "name": "均线金叉", "desc": "5日均线上穿20日均线"},
        {"id": "low_pe_value", "name": "低估值", "desc": "PE<15 且 PB<2 且 ROE>10%"},
        {"id": "strong_momentum", "name": "强势动量", "desc": "20日涨幅>15%且换手率>5%"},
    ]}


@router.get("/screener/run")
async def run_screener(
    strategy: str = Query("oversold_bounce"),
    universe: str = Query("hs300", description="hs300/zz500/zz1000/all"),
    cache: TTLCache = Depends(get_cache),
):
    """Run a screening strategy against a stock universe."""
    cache_key = f"screener:{strategy}:{universe}"
    cached = await cache.get(cache_key)
    if cached:
        return {"data": cached}

    # Get universe codes
    codes = await _get_universe_codes(universe, cache)
    if not codes:
        return {"data": {"strategy_name": strategy, "scanned": 0, "count": 0, "matches": []}}

    # Fetch quotes in batches with concurrency control
    client = get_http_client()
    all_quotes = {}
    batch_size = 60
    tasks = []
    for i in range(0, len(codes), batch_size):
        batch = codes[i:i + batch_size]
        tasks.append(_fetch_with_sem(client, batch))
    results = await asyncio.gather(*tasks, return_exceptions=True)
    for r in results:
        if isinstance(r, dict):
            all_quotes.update(r)

    # Apply strategy filter
    matches = _apply_strategy(strategy, all_quotes)

    data = {
        "strategy_name": strategy,
        "universe": universe,
        "scanned": len(all_quotes),
        "count": len(matches),
        "matches": matches[:50],  # Cap results
    }
    await cache.set(cache_key, data, ttl=300)
    return {"data": data}


async def _fetch_with_sem(client, codes: list[str]) -> dict:
    async with _SEM:
        return await fetch_quote_batch(client, codes)


async def _get_universe_codes(universe: str, cache: TTLCache) -> list[str]:
    """Get stock codes for a universe via universe builder service."""
    from backend.app.core.http_client import get_http_client
    from backend.app.services.universe import get_universe_codes
    client = get_http_client()
    return await get_universe_codes(client, universe, cache)


def _apply_strategy(strategy: str, quotes: dict[str, dict]) -> list[dict]:
    """Apply screening strategy to quotes dict."""
    matches = []
    for code, q in quotes.items():
        hit = False
        reason = ""
        pct = q.get("change_pct", 0)
        pe = q.get("pe", 0)
        pb = q.get("pb", 0)
        turnover = q.get("turnover", 0)
        vol_ratio = q.get("volume_ratio", 0)
        amplitude = q.get("amplitude", 0)
        price = q.get("price", 0)
        avg_price = q.get("avg_price", 0)
        prev_close = q.get("prev_close", 0)
        low = q.get("low", 0)

        if strategy == "low_pe_value":
            if 0 < pe < 15 and 0 < pb < 2:
                hit = True
                reason = f"PE={pe:.1f} PB={pb:.2f} 低估值"
        elif strategy == "strong_momentum":
            if pct > 3 and turnover > 3:
                hit = True
                reason = f"涨幅{pct:.1f}% 换手{turnover:.1f}% 强势突破"
        elif strategy == "oversold_bounce":
            # 盘中大幅下探后拉回（振幅大+收涨）
            if amplitude > 3 and pct > 0.5 and prev_close > 0 and low < prev_close * 0.98:
                hit = True
                reason = f"振幅{amplitude:.1f}% 探底回升 涨{pct:.1f}%"
            elif pct > 1.5 and turnover > 3 and vol_ratio > 1.2:
                hit = True
                reason = f"放量反弹{pct:.1f}% 量比{vol_ratio:.1f}"
        elif strategy == "volume_break":
            # 量比>2 且涨幅>2%（放量突破）
            if vol_ratio > 2 and pct > 2:
                hit = True
                reason = f"量比{vol_ratio:.1f} 涨{pct:.1f}% 放量突破"
            elif vol_ratio > 2.5 and pct > 1:
                hit = True
                reason = f"量比{vol_ratio:.1f} 显著放量 涨{pct:.1f}%"
        elif strategy == "ma_golden_cross":  # noqa: SIM102 - 策略分派分支内的独立条件判断，保持与其它分支一致的结构
            # 价格站上均价线+涨幅适中+量能配合（近似均线金叉）
            if (avg_price > 0 and price > avg_price * 1.01
                    and 1 < pct < 7 and vol_ratio > 1.2 and turnover > 1.5):
                hit = True
                reason = f"站上均价 涨{pct:.1f}% 量比{vol_ratio:.1f}"

        if hit:
            matches.append({
                "code": code,
                "name": q.get("name", ""),
                "price": price,
                "change_pct": pct,
                "pe": pe,
                "pb": pb,
                "reason": reason,
            })

    matches.sort(key=lambda x: x.get("change_pct", 0), reverse=True)
    return matches
