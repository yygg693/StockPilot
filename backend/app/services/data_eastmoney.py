"""East Money (东方财富) data service as fallback data source."""
from __future__ import annotations

import httpx

from backend.app.core.logging import get_logger

logger = get_logger("data_eastmoney")

_HEADERS = {"Referer": "https://quote.eastmoney.com"}


def _em_code(code: str) -> str:
    """Convert internal code (sh600519) to East Money format (1.600519)."""
    if code.startswith("sh"):
        return f"1.{code[2:]}"
    elif code.startswith("sz"):
        return f"0.{code[2:]}"
    return code


async def fetch_kline(
    client: httpx.AsyncClient,
    code: str,
    period: str = "day",
    count: int = 120,
) -> list[dict]:
    """Fetch K-line from East Money (fallback for Tencent).

    period: day/week/month
    Returns list of {date, open, close, high, low, volume}.
    """
    em_c = _em_code(code)
    period_map = {"day": "101", "week": "102", "month": "103"}
    p = period_map.get(period, "101")

    url = (
        f"https://push2his.eastmoney.com/api/qt/stock/kline/get"
        f"?secid={em_c}&fields1=f1,f2,f3,f4,f5,f6"
        f"&fields2=f51,f52,f53,f54,f55,f56,f57,f58"
        f"&klt={p}&fqt=1&beg=0&end=20500101&lmt={count}"
    )
    try:
        r = await client.get(url, headers=_HEADERS, timeout=10.0)
        r.raise_for_status()
        data = r.json()
    except Exception as e:
        logger.warning("eastmoney.kline_failed", code=code, error=str(e))
        return []

    try:
        klines = data["data"]["klines"]
    except (KeyError, TypeError):
        return []

    result = []
    for k in klines:
        # Format: "2024-01-02,open,close,high,low,volume,amount,amplitude"
        parts = k.split(",")
        if len(parts) < 6:
            continue
        try:
            result.append({
                "date": parts[0],
                "open": float(parts[1]),
                "close": float(parts[2]),
                "high": float(parts[3]),
                "low": float(parts[4]),
                "volume": float(parts[5]),
            })
        except (ValueError, IndexError):
            continue
    return result


async def fetch_quote_batch(client: httpx.AsyncClient, codes: list[str]) -> dict[str, dict]:
    """Fetch real-time quotes from East Money (fallback)."""
    results: dict[str, dict] = {}
    # East Money push2 API supports multiple secids
    secids = ",".join(_em_code(c) for c in codes)
    url = (
        f"https://push2.eastmoney.com/api/qt/ulist.np/get"
        f"?secids={secids}&fields=f1,f2,f3,f4,f5,f6,f12,f14,f15,f16,f17"
    )
    try:
        r = await client.get(url, headers=_HEADERS, timeout=8.0)
        r.raise_for_status()
        data = r.json()
    except Exception as e:
        logger.warning("eastmoney.quote_failed", codes=codes[:3], error=str(e))
        return results

    try:
        items = data["data"]["diff"]
    except (KeyError, TypeError):
        return results

    for item in items:
        try:
            em_code_raw = item.get("f12", "")
            market = item.get("f13", 0)
            # Reconstruct internal code
            prefix = "sh" if market == 1 else "sz"
            code = f"{prefix}{em_code_raw}"
            results[code] = {
                "code": code,
                "name": item.get("f14", ""),
                "price": item.get("f2", 0) / 100,  # East Money uses scaled ints
                "prev_close": item.get("f4", 0) / 100,
                "open": item.get("f5", 0) / 100,
                "high": item.get("f15", 0) / 100,
                "low": item.get("f16", 0) / 100,
                "volume": item.get("f5", 0),
                "change": 0,
                "change_pct": item.get("f3", 0) / 100,
                "amount": 0,
            }
        except (KeyError, ValueError, TypeError):
            continue
    return results
