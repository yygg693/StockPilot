"""
智能选基金：基于 AKShare 的可达数据源（东财基金榜单 / ETF 实时行情）。
- ETF：fund_etf_spot_em()（1555 只，含实时涨跌/成交额）
- 场外基金：fund_open_fund_rank_em()（20034 只，含近1周~成立来收益）
策略：
  etf_momentum  ETF 近期强势（按当日涨幅）
  etf_active    ETF 高流动性（按成交额）
  open_year     场外基金 近1年 收益榜
  open_3y       场外基金 近3年 收益榜
  open_steady   场外基金 稳健（近1年/近3年均正，按近3年排序）
所有函数出错时返回结构化 error，不抛异常。
"""
import threading

try:
    import akshare as ak
except Exception:  # noqa
    ak = None

_CACHE = {}
_CACHE_LOCK = threading.Lock()


def _cache_get(key, ttl):
    with _CACHE_LOCK:
        it = _CACHE.get(key)
        if it and (import_time() - it[0]) < ttl:
            return it[1]
    return None


def _cache_set(key, val):
    with _CACHE_LOCK:
        _CACHE[key] = (import_time(), val)


def import_time():
    import time
    return time.time()


def _f(v):
    try:
        if v is None or (isinstance(v, float) and __import__("math").isnan(v)):
            return None
        if isinstance(v, str) and v.strip() in ("", "-", "--", "nan"):
            return None
        return float(v)
    except Exception:  # noqa
        return None


def _etf_spot():
    key = "etf_spot"
    c = _cache_get(key, 120)
    if c is not None:
        return c
    df = ak.fund_etf_spot_em()
    _cache_set(key, df)
    return df


def _open_rank():
    key = "open_rank"
    c = _cache_get(key, 300)
    if c is not None:
        return c
    df = ak.fund_open_fund_rank_em()
    _cache_set(key, df)
    return df


def _etf_rows(df):
    out = []
    for _, r in df.iterrows():
        out.append({
            "code": str(r.get("代码")),
            "name": str(r.get("名称")),
            "price": _f(r.get("最新价")),
            "change_pct": _f(r.get("涨跌幅")),
            "amount": _f(r.get("成交额")),
            "volume": _f(r.get("成交量")),
            "discount": _f(r.get("基金折价率")),
            "iopv": _f(r.get("IOPV实时估值")),
            "scale": _f(r.get("基金规模")) if "基金规模" in df.columns else None,
        })
    return out


def _open_rows(df):
    out = []
    for _, r in df.iterrows():
        out.append({
            "code": str(r.get("基金代码")),
            "name": str(r.get("基金简称")),
            "nav": _f(r.get("单位净值")),
            "acc_nav": _f(r.get("累计净值")),
            "daily": _f(r.get("日增长率")),
            "w1": _f(r.get("近1周")),
            "m1": _f(r.get("近1月")),
            "m3": _f(r.get("近3月")),
            "m6": _f(r.get("近6月")),
            "y1": _f(r.get("近1年")),
            "y2": _f(r.get("近2年")),
            "y3": _f(r.get("近3年")),
            "ytd": _f(r.get("今年来")),
            "since": _f(r.get("成立来")),
            "since_annual": _f(r.get("成立来年化")),
        })
    return out


def screen(strategy: str = "etf_momentum", params: dict = None):
    params = params or {}
    top_n = int(params.get("top_n", 30))
    if ak is None:
        return {"error": "akshare 未安装", "strategy_name": strategy, "count": 0, "items": []}
    try:
        if strategy in ("etf_momentum", "etf_active", "etf"):
            df = _etf_spot()
            rows = _etf_rows(df)
            if strategy == "etf_active":
                rows.sort(key=lambda x: (x["amount"] or 0), reverse=True)
                name = "ETF 高流动性榜（按成交额）"
            else:
                rows.sort(key=lambda x: (x["change_pct"] if x["change_pct"] is not None else -1e9), reverse=True)
                name = "ETF 近期强势榜（按当日涨幅）"
            items = rows[:top_n]
            return {"strategy_name": name, "asset": "etf", "count": len(items), "items": items}

        if strategy == "open_year":
            df = _open_rank()
            rows = _open_rows(df)
            rows = [r for r in rows if r["y1"] is not None]
            rows.sort(key=lambda x: x["y1"], reverse=True)
            return {"strategy_name": "场外基金 近1年 收益榜", "asset": "open", "count": len(rows[:top_n]), "items": rows[:top_n]}

        if strategy == "open_3y":
            df = _open_rank()
            rows = _open_rows(df)
            rows = [r for r in rows if r["y3"] is not None]
            rows.sort(key=lambda x: x["y3"], reverse=True)
            return {"strategy_name": "场外基金 近3年 收益榜", "asset": "open", "count": len(rows[:top_n]), "items": rows[:top_n]}

        if strategy == "open_steady":
            df = _open_rank()
            rows = _open_rows(df)
            rows = [r for r in rows if (r["y1"] or 0) > 0 and (r["y3"] or 0) > 0]
            rows.sort(key=lambda x: (x["y3"] or 0), reverse=True)
            return {"strategy_name": "场外基金 稳健榜（近1年/近3年均为正）", "asset": "open", "count": len(rows[:top_n]), "items": rows[:top_n]}

        return {"error": f"未知策略：{strategy}", "strategy_name": strategy, "count": 0, "items": []}
    except Exception as e:  # noqa
        return {"error": str(e), "strategy_name": strategy, "count": 0, "items": []}
