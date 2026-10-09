"""Sector/industry routes: sector list, sector detail, top movers."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from backend.app.core.cache import TTLCache
from backend.app.core.http_client import get_http_client
from backend.app.core.logging import get_logger
from backend.app.deps import get_cache

logger = get_logger("sector")
router = APIRouter()

# Major sector codes (eastmoney BK codes)
_SECTORS = [
    ("BK0475", "半导体"), ("BK0447", "酿酒行业"), ("BK0448", "医药商业"),
    ("BK0451", "银行"), ("BK0452", "保险"), ("BK0453", "证券"),
    ("BK0454", "房地产"), ("BK0455", "汽车"), ("BK0456", "电力"),
    ("BK0457", "煤炭"), ("BK0458", "钢铁"), ("BK0459", "有色金属"),
    ("BK0460", "化工"), ("BK0461", "建材"), ("BK0462", "建筑"),
    ("BK0463", "机械"), ("BK0464", "军工"), ("BK0465", "电子"),
    ("BK0466", "通信"), ("BK0467", "计算机"), ("BK0468", "传媒"),
    ("BK0469", "食品"), ("BK0470", "纺织"), ("BK0471", "商贸"),
    ("BK0472", "旅游"), ("BK0473", "农业"), ("BK0474", "新能源"),
    ("BK0476", "人工智能"), ("BK0477", "机器人"), ("BK0478", "光伏"),
]


@router.get("/sectors")
async def list_sectors(cache: TTLCache = Depends(get_cache)):
    """Get sector performance calculated from constituent stocks."""
    cached = await cache.get("sectors_overview")
    if cached:
        return {"data": cached}

    client = get_http_client()
    import re as _re

    # Collect all unique stock codes across sectors
    all_codes = set()
    for codes in _SECTOR_STOCKS.values():
        all_codes.update(codes)
    all_codes_list = list(all_codes)

    # Batch fetch all quotes from Tencent
    stock_data: dict[str, dict] = {}
    try:
        # Fetch in chunks of 60
        for i in range(0, len(all_codes_list), 60):
            chunk = ",".join(all_codes_list[i:i+60])
            r = await client.get(
                f"https://qt.gtimg.cn/q={chunk}",
                headers={"Referer": "https://finance.qq.com"},
                timeout=10.0,
            )
            for line in r.text.strip().split(";"):
                line = line.strip()
                if not line or "=" not in line:
                    continue
                m = _re.match(r'v_(\w+)="(.*)"', line)
                if not m:
                    continue
                fields = m.group(2).split("~")
                if len(fields) < 35:
                    continue
                try:
                    stock_data[m.group(1)] = {
                        "name": fields[1],
                        "price": float(fields[3]) if fields[3] else 0,
                        "change_pct": float(fields[32]) if fields[32] else 0,
                        "amount": float(fields[37]) if len(fields) > 37 and fields[37] else 0,
                    }
                except (ValueError, IndexError):
                    continue
    except Exception as e:
        logger.warning("sectors.fetch_failed", error=str(e))

    # Calculate sector averages
    results = []
    names = {s[0]: s[1] for s in _SECTORS}
    for bk_code, stock_codes in _SECTOR_STOCKS.items():
        pcts = []
        total_amount = 0.0
        lead = ""
        lead_pct = -999.0
        for sc in stock_codes:
            sd = stock_data.get(sc)
            if sd:
                pcts.append(sd["change_pct"])
                total_amount += sd["amount"]
                if sd["change_pct"] > lead_pct:
                    lead_pct = sd["change_pct"]
                    lead = sd["name"]
        avg_pct = sum(pcts) / len(pcts) if pcts else 0.0
        results.append({
            "code": bk_code,
            "name": names.get(bk_code, bk_code),
            "price": 0,
            "change_pct": round(avg_pct, 2),
            "turnover": 0,
            "amount": round(total_amount, 0),
            "lead_stock": lead,
            "stock_count": len(pcts),
        })

    # Add sectors without constituent data
    for c, n in _SECTORS:
        if c not in _SECTOR_STOCKS:
            results.append({"code": c, "name": n, "price": 0, "change_pct": 0, "turnover": 0, "amount": 0, "lead_stock": "", "stock_count": 0})

    results.sort(key=lambda x: x.get("change_pct", 0), reverse=True)
    await cache.set("sectors_overview", results, ttl=60)
    return {"data": results}


# Sector constituent stocks (representative names per sector)
_SECTOR_STOCKS: dict[str, list[str]] = {
    "BK0475": ["sh688981", "sz002371", "sh603501", "sz300782", "sh688012", "sz002049", "sh603986", "sz300661"],
    "BK0447": ["sh600519", "sz000858", "sh600809", "sz000568", "sh603369", "sz002304", "sh600702", "sz000799"],
    "BK0448": ["sh600276", "sz300760", "sh603259", "sz002821", "sh600196", "sz300015", "sh600436", "sz002007"],
    "BK0451": ["sh601398", "sh600036", "sh601166", "sh600000", "sh601328", "sh601939", "sh601288", "sh600016"],
    "BK0452": ["sh601318", "sh601601", "sh601628", "sh601336", "sh601319", "sh600030"],
    "BK0453": ["sh600030", "sh601688", "sh601211", "sz000776", "sh600999", "sz002736", "sh601066"],
    "BK0454": ["sz000002", "sh600048", "sh601155", "sz001979", "sh600383", "sz000069"],
    "BK0455": ["sz002594", "sh600104", "sh601633", "sz000625", "sh600418", "sz002920"],
    "BK0456": ["sh600900", "sh600886", "sh600025", "sz003816", "sh601985", "sh600011"],
    "BK0457": ["sh601088", "sh601225", "sh600188", "sz000983", "sh601898", "sh600348"],
    "BK0459": ["sh601899", "sz002460", "sh600362", "sz000878", "sh601600", "sz002466"],
    "BK0460": ["sh600309", "sz002648", "sh600426", "sz000830", "sh600352", "sz002493"],
    "BK0465": ["sz002415", "sh600584", "sz002241", "sh603160", "sz002456", "sh600745"],
    "BK0467": ["sz002230", "sh600588", "sz002410", "sh600845", "sz300033", "sh688111"],
    "BK0474": ["sz300750", "sh601012", "sz002459", "sh600438", "sz300274", "sh688599"],
    "BK0476": ["sz002230", "sh688256", "sz300496", "sh688047", "sz002415", "sh688561"],
    "BK0458": ["sh600019", "sh600022", "sz000709", "sh600010", "sz000898", "sh600569"],
    "BK0461": ["sh600585", "sz002271", "sh600801", "sz000401", "sh601100"],
    "BK0462": ["sh601668", "sh601186", "sh601800", "sz000090", "sh600170"],
    "BK0463": ["sh601766", "sz000425", "sh600031", "sz002008", "sh601100"],
    "BK0464": ["sh600893", "sz000768", "sh600760", "sz002013", "sh601989"],
    "BK0466": ["sh600050", "sz000063", "sh600487", "sz002281", "sh600522"],
    "BK0468": ["sz300413", "sz002607", "sh603444", "sz300251", "sh601595"],
    "BK0469": ["sh600887", "sz000895", "sh603288", "sz002507", "sh600872"],
    "BK0470": ["sz002042", "sh600400", "sz002563", "sh601339"],
    "BK0471": ["sz002024", "sh600697", "sz000417", "sh600729"],
    "BK0472": ["sh600138", "sz000888", "sh600054", "sz002033"],
    "BK0473": ["sz000998", "sh600598", "sz002311", "sh600127", "sz002385"],
    "BK0477": ["sz300124", "sh688169", "sz002747", "sh603728", "sz300024"],
    "BK0478": ["sz300750", "sh601012", "sz002459", "sh600438", "sz300274"],
}


@router.get("/sector/stocks")
async def sector_stocks(
    sector: str = Query(..., description="BK code e.g. BK0475"),
    limit: int = Query(20, ge=1, le=50),
    cache: TTLCache = Depends(get_cache),
):
    """Get top stocks in a sector via Tencent quotes."""
    cache_key = f"sector_stocks:{sector}"
    cached = await cache.get(cache_key)
    if cached:
        return {"data": cached}

    client = get_http_client()
    codes = _SECTOR_STOCKS.get(sector, [])
    if not codes:
        # Fallback: use mover pool
        codes = _MOVER_POOL.split(",")[:10]

    stocks = []
    try:
        import re as _re
        code_str = ",".join(codes[:limit])
        r = await client.get(
            f"https://qt.gtimg.cn/q={code_str}",
            headers={"Referer": "https://finance.qq.com"},
            timeout=10.0,
        )
        for line in r.text.strip().split(";"):
            line = line.strip()
            if not line or "=" not in line:
                continue
            m = _re.match(r'v_(\w+)="(.*)"', line)
            if not m:
                continue
            fields = m.group(2).split("~")
            if len(fields) < 35:
                continue
            try:
                stocks.append({
                    "code": m.group(1),
                    "name": fields[1],
                    "price": float(fields[3]) if fields[3] else 0,
                    "change_pct": float(fields[32]) if fields[32] else 0,
                    "change": float(fields[31]) if fields[31] else 0,
                    "volume": float(fields[6]) if fields[6] else 0,
                    "amount": float(fields[37]) if len(fields) > 37 and fields[37] else 0,
                    "high": float(fields[33]) if len(fields) > 33 and fields[33] else 0,
                    "low": float(fields[34]) if len(fields) > 34 and fields[34] else 0,
                    "open": float(fields[5]) if fields[5] else 0,
                    "prev_close": float(fields[4]) if fields[4] else 0,
                })
            except (ValueError, IndexError):
                continue
    except Exception as e:
        logger.warning("sector_stocks.failed", sector=sector, error=str(e))

    stocks.sort(key=lambda x: x.get("change_pct", 0), reverse=True)
    await cache.set(cache_key, stocks, ttl=60)
    return {"data": stocks}


# Large pool of liquid stocks for top-movers ranking
_MOVER_POOL = (
    "sh600519,sh601318,sz000858,sh600036,sz300750,sh601012,sz002594,sh600900,"
    "sz000001,sh601899,sh600030,sz002475,sh600276,sz300059,sh601888,sz000333,"
    "sh600809,sz002304,sh601166,sh600887,sh601398,sh600000,sz000002,sh601668,"
    "sh600585,sz002415,sh601601,sh600104,sz000568,sh601088,sh600309,sz002714,"
    "sh600690,sz000725,sh601225,sz300124,sh600031,sz002352,sh601633,sz000651,"
    "sh600048,sz002027,sh601857,sh600050,sz300760,sh601919,sz002230,sh600588,"
    "sz000063,sh601006,sh600150,sz002049,sh601766,sz300015,sh600436,sz002142,"
    "sh601390,sh600089,sz000977,sh601138,sz300122,sh600703,sz002460,sh601688"
)


@router.get("/top-movers")
async def top_movers(
    direction: str = Query("up", description="up/down"),
    limit: int = Query(10, ge=1, le=30),
    cache: TTLCache = Depends(get_cache),
):
    """Get top gainers or losers from a liquid stock pool via Tencent API."""
    cache_key = f"top_movers:{direction}:{limit}"
    cached = await cache.get(cache_key)
    if cached:
        return {"data": cached}

    client = get_http_client()
    stocks = []
    try:
        import re as _re
        r = await client.get(
            f"https://qt.gtimg.cn/q={_MOVER_POOL}",
            headers={"Referer": "https://finance.qq.com"},
            timeout=10.0,
        )
        for line in r.text.strip().split(";"):
            line = line.strip()
            if not line or "=" not in line:
                continue
            m = _re.match(r'v_(\w+)="(.*)"', line)
            if not m:
                continue
            fields = m.group(2).split("~")
            if len(fields) < 35:
                continue
            try:
                stocks.append({
                    "code": m.group(1),
                    "name": fields[1],
                    "price": float(fields[3]) if fields[3] else 0,
                    "change_pct": float(fields[32]) if fields[32] else 0,
                    "amount": float(fields[37]) if len(fields) > 37 and fields[37] else 0,
                })
            except (ValueError, IndexError):
                continue
    except Exception as e:
        logger.warning("top_movers.failed", error=str(e))

    reverse = direction == "up"
    stocks.sort(key=lambda x: x.get("change_pct", 0), reverse=reverse)
    stocks = stocks[:limit]
    await cache.set(cache_key, stocks, ttl=30)
    return {"data": stocks}
