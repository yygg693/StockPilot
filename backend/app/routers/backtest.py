"""Backtest routes: professional strategy backtesting with trading costs and risk metrics."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from backend.app.core.cache import TTLCache
from backend.app.core.http_client import get_http_client
from backend.app.core.logging import get_logger
from backend.app.deps import get_cache
from backend.app.services.backtest_engine import TradeCost, run_backtest
from backend.app.services.data_source import get_kline

logger = get_logger("backtest")
router = APIRouter()


@router.get("/backtest/run")
async def run_backtest_api(
    code: str = Query(..., description="Stock code e.g. sh600519"),
    strategy: str = Query("ma_cross", description="ma_cross/bollinger/momentum"),
    days: int = Query(250, ge=60, le=1000),
    commission: float = Query(0.00025, ge=0, le=0.01, description="Commission rate"),
    slippage: float = Query(0.001, ge=0, le=0.05, description="Slippage rate"),
    cache: TTLCache = Depends(get_cache),
):
    """Run a professional backtest with trading costs, slippage, and risk metrics."""
    cache_key = f"backtest:{code}:{strategy}:{days}:{commission}:{slippage}"
    cached = await cache.get(cache_key)
    if cached:
        return {"data": cached}

    client = get_http_client()
    klines = await get_kline(client, code, period="day", count=days)
    if len(klines) < 30:
        return {"data": {"error": "Insufficient data for backtest"}}

    # Configure trading costs
    cost_config = TradeCost(
        commission_rate=commission,
        slippage=slippage,
    )

    # Run professional backtest
    result = run_backtest(
        klines=klines,
        strategy=strategy,
        cost_config=cost_config,
    )

    # Add metadata
    result.summary["code"] = code
    result.summary["strategy"] = strategy
    result.summary["period_days"] = len(klines)

    output = {
        "trades": result.trades,
        "equity_curve": result.equity_curve,
        "summary": result.summary,
    }

    await cache.set(cache_key, output, ttl=600)
    return {"data": output}
