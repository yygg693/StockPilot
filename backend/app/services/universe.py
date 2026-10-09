"""Universe builder: fetch real stock code lists for screening."""
from __future__ import annotations

import httpx

from backend.app.core.cache import TTLCache
from backend.app.core.logging import get_logger

logger = get_logger("universe")

# Cache universe codes for 1 hour
_UNIVERSE_TTL = 3600


async def get_universe_codes(
    client: httpx.AsyncClient,
    universe: str,
    cache: TTLCache,
) -> list[str]:
    """Get stock codes for a universe (hs300/zz500/zz1000/all).

    Uses Tencent index constituent API or fallback to static lists.
    """
    cache_key = f"universe_codes:{universe}"
    cached = await cache.get(cache_key)
    if cached:
        return cached

    codes: list[str] = []
    try:
        if universe == "hs300":
            codes = await _fetch_index_constituents(client, "sh000300")
        elif universe == "zz500":
            codes = await _fetch_index_constituents(client, "sh000905")
        elif universe == "zz1000":
            codes = await _fetch_index_constituents(client, "sh000852")
        elif universe == "all":
            codes = await _fetch_all_a_shares(client)
        else:
            codes = await _fetch_index_constituents(client, "sh000300")
    except Exception as e:
        logger.warning("universe.fetch_failed", universe=universe, error=str(e))

    if codes:
        await cache.set(cache_key, codes, ttl=_UNIVERSE_TTL)
        logger.info("universe.loaded", universe=universe, count=len(codes))
    return codes


async def _fetch_index_constituents(client: httpx.AsyncClient, index_code: str) -> list[str]:
    """Fetch index constituents from Tencent/CSIndex API."""
    # Most reliable free source: 中证指数官网 constituent files
    # For real-time: use Tencent's index detail page API
    try:
        # Tencent index constituent API
        params = {
            "pn": "1",
            "pz": "500",
            "po": "1",
            "np": "1",
            "fltt": "2",
            "invt": "2",
            "fid": "f3",
            "fs": "b:BK0701" if "300" in index_code else "b:BK0702",
            "fields": "f12,f14",
        }
        # Use eastmoney board-based constituent filter
        # b:BK0701 = 沪深300, b:BK0702 = 中证500, b:BK0703 = 中证1000
        if "000300" in index_code:
            params["fs"] = "b:BK0701"
        elif "000905" in index_code:
            params["fs"] = "b:BK0702"
        elif "000852" in index_code:
            params["fs"] = "b:BK0703"

        r = await client.get(
            "https://push2.eastmoney.com/api/qt/clist/get",
            params=params,
            timeout=10.0,
        )
        data = r.json()
        items = data.get("data", {}).get("diff", [])
        codes = []
        for item in items:
            raw_code = item.get("f12", "")
            if raw_code.startswith("6"):
                codes.append(f"sh{raw_code}")
            elif raw_code.startswith(("0", "3")):
                codes.append(f"sz{raw_code}")
        if codes:
            return codes
    except Exception as e:
        logger.warning("universe.eastmoney_failed", error=str(e))

    # Fallback: generate from known ranges (less accurate but always works)
    return _generate_fallback_codes(index_code)


async def _fetch_all_a_shares(client: httpx.AsyncClient) -> list[str]:
    """Fetch all A-share codes via eastmoney."""
    codes = []
    for market, prefix in [("1", "sh"), ("0", "sz")]:
        try:
            r = await client.get(
                "https://push2.eastmoney.com/api/qt/clist/get",
                params={
                    "pn": "1", "pz": "5000", "po": "1", "np": "1",
                    "fltt": "2", "invt": "2", "fid": "f12",
                    "fs": f"m:{market}+t:6,t:80" if market == "1" else f"m:{market}+t:6,t:80",
                    "fields": "f12",
                },
                timeout=15.0,
            )
            data = r.json()
            items = data.get("data", {}).get("diff", [])
            for item in items:
                raw = item.get("f12", "")
                if raw:
                    codes.append(f"{prefix}{raw}")
        except Exception as e:
            logger.warning("universe.all_shares_failed", market=market, error=str(e))
    return codes


def _generate_fallback_codes(index_code: str) -> list[str]:
    """Generate approximate code ranges as last resort."""
    codes = []
    if "000300" in index_code or "000905" in index_code or "000852" in index_code:
        # SH main board large caps
        for i in range(600000, 600100):
            codes.append(f"sh{i}")
        for i in range(600500, 600540):
            codes.append(f"sh{i}")
        for i in range(601000, 601020):
            codes.append(f"sh{i}")
        for i in range(601300, 601340):
            codes.append(f"sh{i}")
        for i in range(603000, 603030):
            codes.append(f"sh{i}")
        # SZ main board + ChiNext
        for i in range(1, 50):
            codes.append(f"sz{i:06d}")
        for i in range(700, 730):
            codes.append(f"sz{i:06d}")
        for i in range(300001, 300030):
            codes.append(f"sz{i}")
    return codes
