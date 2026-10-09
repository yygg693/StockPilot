"""Fund screener routes with real data from eastmoney."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from backend.app.core.cache import TTLCache
from backend.app.core.http_client import get_http_client
from backend.app.core.logging import get_logger
from backend.app.deps import get_cache
from backend.app.services.data_tencent import fetch_quote_batch

logger = get_logger("fund")
router = APIRouter()


@router.get("/fund/screen")
async def screen_funds(
    fund_type: str = Query("all", description="all/stock/bond/index/mixed"),
    sort_by: str = Query("return_1y", description="return_1y/return_3y/sharpe"),
    limit: int = Query(20, ge=1, le=100),
    cache: TTLCache = Depends(get_cache),
):
    """Screen funds by type and performance via eastmoney fund API."""
    cache_key = f"fund_screen:{fund_type}:{sort_by}:{limit}"
    cached = await cache.get(cache_key)
    if cached:
        return {"data": cached}

    client = get_http_client()
    funds = []

    # eastmoney fund rank API
    type_map = {"all": "", "stock": "gp", "bond": "zq", "index": "zs", "mixed": "hh"}
    ft = type_map.get(fund_type, "")

    try:
        r = await client.get(
            "https://fundapi.eastmoney.com/fundapi/Rank_SYRankExchange",
            params={
                "code": "",
                "sdate": "",
                "edate": "",
                "orderby": "SYL_1N",
                "sort": "desc",
                "rtype": "",
                "dx": "1",
                "tp": ft,
                "isbuy": "0",
                "clrq": "",
                "pageindex": "1",
                "pagesize": str(limit),
            },
            timeout=10.0,
        )
        data = r.json()
        items = data.get("Data", {}).get("list", []) or data.get("data", {}).get("list", [])
        for item in items:
            funds.append({
                "code": item.get("CODE", item.get("code", "")),
                "name": item.get("SHORTNAME", item.get("name", "")),
                "type": item.get("FTYPE", item.get("type", "")),
                "nav": item.get("NAV", item.get("nav", 0)),
                "return_1y": _safe_float(item.get("SYL_1N", item.get("return_1y", 0))),
                "return_6m": _safe_float(item.get("SYL_6Y", item.get("return_6m", 0))),
                "return_3m": _safe_float(item.get("SYL_3Y", item.get("return_3m", 0))),
            })
    except Exception as e:
        logger.warning("fund.screen_failed", error=str(e))
        # Fallback: try alternative API
        try:
            r = await client.get(
                "https://fund.eastmoney.com/data/rankhandler.aspx",
                params={
                    "op": "ph", "dt": "kf", "ft": ft, "rs": "", "gs": "0",
                    "sc": "1nzf", "st": "desc", "sd": "", "ed": "",
                    "qdii": "", "tabSubtype": ",,,,,", "pi": "1", "pn": str(limit),
                    "dx": "1",
                },
                headers={"Referer": "https://fund.eastmoney.com/data/fundranking.html"},
                timeout=10.0,
            )
            text = r.text
            # Parse: var rankData = {datas:["code,name,..."],...}
            import re
            m = re.search(r'datas:\[(.*?)\]', text)
            if m and m.group(1):
                items = m.group(1).split('","')
                for item in items[:limit]:
                    parts = item.replace('"', "").split(",")
                    if len(parts) >= 20:
                        funds.append({
                            "code": parts[0],
                            "name": parts[1],
                            "type": fund_type,
                            "nav": _safe_float(parts[4]),
                            "return_1m": _safe_float(parts[8]),
                            "return_3m": _safe_float(parts[9]),
                            "return_6m": _safe_float(parts[10]),
                            "return_1y": _safe_float(parts[11]),
                            "return_ytd": _safe_float(parts[14]) if len(parts) > 14 else 0,
                        })
        except Exception as e2:
            logger.warning("fund.fallback_failed", error=str(e2))

    result = {"funds": funds, "total": len(funds)}
    await cache.set(cache_key, result, ttl=600)
    return {"data": result}


@router.get("/fund/detail")
async def fund_detail(code: str = Query(...), cache: TTLCache = Depends(get_cache)):
    """Get comprehensive fund data from eastmoney pingzhongdata."""
    # Strip exchange prefix (sz/sh) — eastmoney expects raw fund code
    raw_code = code.removeprefix("sz").removeprefix("sh")
    cache_key = f"fund_detail:{raw_code}"
    cached = await cache.get(cache_key)
    if cached:
        return {"data": cached}

    client = get_http_client()
    detail = {
        "code": raw_code, "name": "", "type": "", "nav": 0,
        "manager": "", "manager_star": 0, "manager_work_time": "", "manager_fund_size": "",
        "scale": "", "inception": "",
        "return_1m": 0, "return_3m": 0, "return_6m": 0, "return_1y": 0, "return_ytd": 0, "return_3y": 0,
        "fee_original": "", "fee_discount": "", "fee_min_purchase": "",
        "nav_history": [],
        "top_holdings": [],
        "asset_allocation": {},
        "performance_scores": {},
        "scale_history": [],
        "holder_structure": [],
        "similar_rank": [],
    }

    try:
        import json as _json
        import re as _re
        r = await client.get(
            f"https://fund.eastmoney.com/pingzhongdata/{raw_code}.js",
            headers={"Referer": "https://fund.eastmoney.com", "User-Agent": "Mozilla/5.0"},
            timeout=15.0,
        )
        text = r.text

        # Basic info
        m = _re.search(r'var fS_name = "(.*?)"', text)
        if m:
            detail["name"] = m.group(1)

        # Fees
        m = _re.search(r'fund_sourceRate="(.*?)"', text)
        if m:
            detail["fee_original"] = m.group(1)
        m = _re.search(r'fund_Rate="(.*?)"', text)
        if m:
            detail["fee_discount"] = m.group(1)
        m = _re.search(r'fund_minsg="(.*?)"', text)
        if m:
            detail["fee_min_purchase"] = m.group(1)

        # Returns
        m = _re.search(r'var syl_1n="(.*?)"', text)
        if m:
            detail["return_1y"] = _safe_float(m.group(1))
        m = _re.search(r'var syl_6y="(.*?)"', text)
        if m:
            detail["return_6m"] = _safe_float(m.group(1))
        m = _re.search(r'var syl_3y="(.*?)"', text)
        if m:
            detail["return_3m"] = _safe_float(m.group(1))
        m = _re.search(r'var syl_1y="(.*?)"', text)
        if m:
            detail["return_1m"] = _safe_float(m.group(1))

        # Top stock holdings (market.code format)
        m = _re.search(r'stockCodesNew\s*=\s*\[(.*?)\]', text)
        if m and m.group(1).strip():
            codes_raw = m.group(1).replace('"', '').split(',')
            for c in codes_raw[:10]:
                c = c.strip()
                if '.' in c:
                    parts = c.split('.')
                    detail["top_holdings"].append({"market": parts[0], "code": parts[1]})

        # Manager info (bracket-counting for nested JSON)
        mgr_idx = text.find("Data_currentFundManager")
        if mgr_idx != -1:
            mgr_arr_start = text.find("[", mgr_idx)
            if mgr_arr_start != -1:
                depth = 0
                mgr_arr_end = mgr_arr_start
                for ci in range(mgr_arr_start, min(mgr_arr_start + 10000, len(text))):
                    if text[ci] == "[":
                        depth += 1
                    elif text[ci] == "]":
                        depth -= 1
                    if depth == 0:
                        mgr_arr_end = ci
                        break
                try:
                    managers = _json.loads(text[mgr_arr_start:mgr_arr_end + 1])
                    if managers:
                        mgr = managers[0]
                        detail["manager"] = mgr.get("name", "")
                        detail["manager_star"] = mgr.get("star", 0)
                        detail["manager_work_time"] = mgr.get("workTime", "")
                        detail["manager_fund_size"] = mgr.get("fundSize", "")
                except Exception:
                    nm = _re.search(r'"name":"(.*?)"', text[mgr_idx:mgr_idx+500])
                    if nm:
                        detail["manager"] = nm.group(1)

        # Performance evaluation (5 dimensions)
        m = _re.search(r'Data_performanceEvaluation\s*=\s*(\{.*?\});', text, _re.DOTALL)
        if m:
            try:
                pe = _json.loads(m.group(1))
                detail["performance_scores"] = {
                    "average": pe.get("avr", ""),
                    "categories": pe.get("categories", []),
                    "scores": pe.get("data", []),
                }
            except Exception:
                pass

        # Asset allocation
        m = _re.search(r'Data_assetAllocation\s*=\s*(\{.*?\});', text, _re.DOTALL)
        if m:
            try:
                aa = _json.loads(m.group(1))
                detail["asset_allocation"] = {
                    "categories": aa.get("categories", []),
                    "series": [{"name": s.get("name", ""), "data": s.get("data", [])} for s in aa.get("series", [])],
                }
            except Exception:
                pass

        # Scale history
        m = _re.search(r'Data_fluctuationScale\s*=\s*(\{.*?\});', text, _re.DOTALL)
        if m:
            try:
                fs = _json.loads(m.group(1))
                cats = fs.get("categories", [])
                series = fs.get("series", [])
                detail["scale_history"] = [
                    {"date": cats[i], "scale": series[i].get("y", 0), "change": series[i].get("mom", "")}
                    for i in range(min(len(cats), len(series)))
                ]
                if series:
                    detail["scale"] = str(series[-1].get("y", ""))
            except Exception:
                pass

        # Holder structure
        m = _re.search(r'Data_holderStructure\s*=\s*(\{.*?\});', text, _re.DOTALL)
        if m:
            try:
                hs = _json.loads(m.group(1))
                cats = hs.get("categories", [])
                series = hs.get("series", [])
                detail["holder_structure"] = {
                    "categories": cats,
                    "series": [{"name": s.get("name", ""), "data": s.get("data", [])} for s in series],
                }
            except Exception:
                pass

        # Similar type rank (recent)
        m = _re.search(r'Data_rateInSimilarType\s*=\s*(\[.*?\]);', text, _re.DOTALL)
        if m:
            try:
                ranks = _json.loads(m.group(1))
                # Take last 10 entries
                detail["similar_rank"] = ranks[-10:] if len(ranks) > 10 else ranks
            except Exception:
                pass

        # NAV history (bracket-counting for large array)
        nwt_idx = text.find("Data_netWorthTrend")
        if nwt_idx != -1:
            arr_start = text.find("[", nwt_idx)
            if arr_start != -1:
                depth = 0
                arr_end = arr_start
                for ci in range(arr_start, min(arr_start + 600000, len(text))):
                    if text[ci] == "[":
                        depth += 1
                    elif text[ci] == "]":
                        depth -= 1
                    if depth == 0:
                        arr_end = ci
                        break
                try:
                    trends = _json.loads(text[arr_start:arr_end + 1])
                    if trends:
                        detail["nav"] = trends[-1].get("y", 0)
                        recent = trends[-250:]
                        detail["nav_history"] = [[t["x"], t["y"]] for t in recent]
                        from datetime import datetime as _dt
                        first_ts = trends[0].get("x", 0)
                        if first_ts:
                            detail["inception"] = _dt.fromtimestamp(first_ts / 1000).strftime("%Y-%m-%d")
                except Exception:
                    pass

    except Exception as e:
        logger.warning("fund.detail_failed", code=code, error=str(e))

    # Calculate YTD return from nav_history
    if detail["nav_history"] and detail["nav"]:
        try:
            from datetime import datetime as _dt2
            year_start = _dt2(_dt2.now().year, 1, 1).timestamp() * 1000
            # Find first NAV entry of current year
            base_nav = None
            for ts, nav in detail["nav_history"]:
                if ts >= year_start:
                    base_nav = nav
                    break
            if base_nav and base_nav > 0:
                detail["return_ytd"] = round((detail["nav"] - base_nav) / base_nav * 100, 2)
        except Exception:
            pass

    # Resolve top_holdings stock names via Tencent quote API
    if detail["top_holdings"]:
        try:
            codes_with_prefix = []
            for h in detail["top_holdings"]:
                prefix = "sh" if h.get("market") == "1" else "sz"
                codes_with_prefix.append(prefix + h["code"])
            quotes = await fetch_quote_batch(client, codes_with_prefix)
            for h in detail["top_holdings"]:
                prefix = "sh" if h.get("market") == "1" else "sz"
                full_code = prefix + h["code"]
                q = quotes.get(full_code)
                if q:
                    h["name"] = q.get("name", h["code"])
                    h["price"] = q.get("price", 0)
                    h["change_pct"] = q.get("change_pct", 0)
                else:
                    h["name"] = h["code"]
        except Exception as e:
            logger.warning("fund.holdings_name_failed", error=str(e))
            for h in detail["top_holdings"]:
                h["name"] = h["code"]

    await cache.set(cache_key, detail, ttl=300)
    return {"data": detail}



def _safe_float(v) -> float:
    try:
        if isinstance(v, str):
            v = v.replace("%", "").replace(",", "")
        return float(v) if v else 0.0
    except (ValueError, TypeError):
        return 0.0
