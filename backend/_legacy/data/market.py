"""
数据服务：基于 AKShare 封装 A股/基金/ETF 的行情、K线、搜索、新闻。
带轻量内存缓存，降低对数据源的压力。
所有函数出错时返回结构化的 error，不抛异常给上层。
"""
import time
import threading
from datetime import datetime

import pandas as pd

from backend.data import tencent
from backend.config import CONFIG

# TTL 从 config.yaml 读取（quote_ttl 单位秒，kline_ttl/news_ttl 单位分钟）
_cache_cfg = CONFIG.get("cache", {})
_TTL_QUOTE = _cache_cfg.get("quote_ttl", 3)
_TTL_KLINE = _cache_cfg.get("kline_ttl", 30) * 60
_TTL_NEWS = _cache_cfg.get("news_ttl", 30) * 60

try:
    import akshare as ak
except Exception as e:  # noqa
    ak = None
    _AK_IMPORT_ERROR = str(e)
else:
    _AK_IMPORT_ERROR = None

# ------------------------------------------------------------------ 缓存
_CACHE = {}
_CACHE_LOCK = threading.Lock()


def _cache_get(key, ttl_seconds):
    with _CACHE_LOCK:
        item = _CACHE.get(key)
        if item and (time.time() - item[0]) < ttl_seconds:
            return item[1]
    return None


def _cache_set(key, value):
    with _CACHE_LOCK:
        _CACHE[key] = (time.time(), value)


def _check_ak():
    if ak is None:
        raise RuntimeError(f"akshare 未安装或导入失败: {_AK_IMPORT_ERROR}")


# ------------------------------------------------------------------ 工具
def classify_code(code: str) -> str:
    """粗略判断代码类型: stock / fund / etf。
    - 6 位数字，15/16/51/159/510/512 等常见 ETF 前缀 -> etf
    - 6 位数字其余 -> stock
    - 其他（如基金代码也是6位，难以纯规则区分）默认 stock，前端可显式指定 type
    """
    code = (code or "").strip()
    if len(code) == 6 and code.isdigit():
        if code[:2] in ("15", "16", "51", "56", "58"):
            return "etf"
        return "stock"
    return "stock"


# ------------------------------------------------------------------ 搜索
def search(keyword: str):
    """按代码或名称搜索股票 / 基金。优先腾讯智能盒子，失败回退 akshare。"""
    keyword = (keyword or "").strip()
    if not keyword:
        return []
    # 优先腾讯（本环境稳定）
    try:
        tx = tencent.search(keyword)
        if tx:
            return tx
    except Exception as e:  # noqa
        print(f"[search] 腾讯搜索失败，回退 akshare: {e}")
    if ak is None:
        return []
    results = []
    # 1) 股票（含 A股主板/创业板/科创板）
    try:
        cache_key = "stock_spot_list"
        df = _cache_get(cache_key, 300)
        if df is None:
            df = ak.stock_zh_a_spot_em()
            _cache_set(cache_key, df)
        m = df[df["代码"].str.contains(keyword, na=False) |
               df["名称"].str.contains(keyword, na=False)]
        for _, r in m.head(15).iterrows():
            results.append({
                "code": str(r["代码"]), "name": str(r["名称"]),
                "type": "stock",
                "price": _f(r.get("最新价")), "change_pct": _f(r.get("涨跌幅")),
            })
    except Exception as e:  # noqa
        print(f"[search] 股票搜索失败: {e}")
    # 2) 基金（名称搜索）
    try:
        cache_key = "fund_name_list"
        fdf = _cache_get(cache_key, 3600)
        if fdf is None:
            fdf = ak.fund_name_em()
            _cache_set(cache_key, fdf)
        code_col = "基金代码" if "基金代码" in fdf.columns else fdf.columns[0]
        name_col = "基金简称" if "基金简称" in fdf.columns else fdf.columns[2]
        fm = fdf[fdf[code_col].astype(str).str.contains(keyword, na=False) |
                 fdf[name_col].astype(str).str.contains(keyword, na=False)]
        for _, r in fm.head(15).iterrows():
            results.append({
                "code": str(r[code_col]), "name": str(r[name_col]),
                "type": "fund", "price": None, "change_pct": None,
            })
    except Exception as e:  # noqa
        print(f"[search] 基金搜索失败: {e}")
    return results


# ------------------------------------------------------------------ 实时行情
def get_quote(code: str, asset_type: str = None):
    """获取单个标的的实时/最新行情摘要。股票/ETF 优先腾讯，基金走 akshare。"""
    asset_type = asset_type or classify_code(code)
    key = f"quote:{asset_type}:{code}"
    cached = _cache_get(key, _TTL_QUOTE)
    if cached:
        return cached
    # 股票 / ETF / 港股 / 美股 优先腾讯
    if asset_type in ("stock", "etf", "hk", "us"):
        try:
            data = tencent.get_quote(code, asset_type)
            _cache_set(key, data)
            return data
        except Exception as e:  # noqa
            print(f"[quote] 腾讯失败，回退 akshare: {e}")
    try:
        _check_ak()
        if asset_type == "fund":
            data = _fund_quote(code)
        else:
            data = _stock_quote(code)
        _cache_set(key, data)
        return data
    except Exception as e:  # noqa
        return {"code": code, "type": asset_type, "error": str(e)}


def _stock_quote(code: str):
    df = _cache_get("stock_spot_list", 3)
    if df is None:
        df = ak.stock_zh_a_spot_em()
        _cache_set("stock_spot_list", df)
    row = df[df["代码"] == code]
    if row.empty:
        # 可能是 ETF
        try:
            edf = ak.fund_etf_spot_em()
            erow = edf[edf["代码"] == code]
            if not erow.empty:
                r = erow.iloc[0]
                return {"code": code, "name": str(r.get("名称")), "type": "etf",
                        "price": _f(r.get("最新价")), "change_pct": _f(r.get("涨跌幅")),
                        "change": _f(r.get("涨跌额")), "open": _f(r.get("开盘价")),
                        "high": _f(r.get("最高价")), "low": _f(r.get("最低价")),
                        "volume": _f(r.get("成交量")), "amount": _f(r.get("成交额"))}
        except Exception:  # noqa
            pass
        return {"code": code, "type": "stock", "error": "未找到该代码行情"}
    r = row.iloc[0]
    return {
        "code": code, "name": str(r.get("名称")), "type": "stock",
        "price": _f(r.get("最新价")), "change_pct": _f(r.get("涨跌幅")),
        "change": _f(r.get("涨跌额")), "open": _f(r.get("今开")),
        "high": _f(r.get("最高")), "low": _f(r.get("最低")),
        "volume": _f(r.get("成交量")), "amount": _f(r.get("成交额")),
        "pe": _f(r.get("市盈率-动态")), "pb": _f(r.get("市净率")),
        "turnover": _f(r.get("换手率")),
    }


def _fund_quote(code: str):
    """场外基金：用最新净值作为 price。"""
    name = _fund_name(code)
    nav_df = ak.fund_open_fund_info_em(symbol=code, indicator="单位净值走势")
    if nav_df is None or nav_df.empty:
        return {"code": code, "name": name, "type": "fund", "error": "无净值数据"}
    nav_df = nav_df.tail(2)
    last = nav_df.iloc[-1]
    price = _f(last.get("单位净值"))
    change_pct = _f(last.get("日增长率"))
    return {"code": code, "name": name, "type": "fund",
            "price": price, "change_pct": change_pct,
            "date": str(last.get("净值日期"))}


def _fund_name(code: str):
    try:
        fdf = _cache_get("fund_name_list", 3600)
        if fdf is None:
            fdf = ak.fund_name_em()
            _cache_set("fund_name_list", fdf)
        code_col = "基金代码" if "基金代码" in fdf.columns else fdf.columns[0]
        name_col = "基金简称" if "基金简称" in fdf.columns else fdf.columns[2]
        row = fdf[fdf[code_col].astype(str) == code]
        if not row.empty:
            return str(row.iloc[0][name_col])
    except Exception:  # noqa
        pass
    return code


# ------------------------------------------------------------------ K线 / 净值
def get_kline(code: str, asset_type: str = None, period: str = "daily", limit: int = 120):
    """K线（股票/ETF）或净值走势（基金）。股票/ETF 优先腾讯，基金走 akshare。"""
    asset_type = asset_type or classify_code(code)
    key = f"kline:{asset_type}:{code}:{period}:{limit}"
    cached = _cache_get(key, _TTL_KLINE)
    if cached:
        return cached
    if asset_type in ("stock", "etf", "hk", "us"):
        try:
            data = tencent.get_kline(code, asset_type, period, limit)
            if data.get("rows"):
                _cache_set(key, data)
                return data
        except Exception as e:  # noqa
            print(f"[kline] 腾讯失败，回退 akshare: {e}")
    try:
        _check_ak()
        if asset_type == "fund":
            data = _fund_nav_series(code, limit)
        else:
            data = _stock_kline(code, asset_type, period, limit)
        _cache_set(key, data)
        return data
    except Exception as e:  # noqa
        return {"code": code, "type": asset_type, "error": str(e), "rows": []}


def get_minute(code: str, asset_type: str = None):
    """分时/日内实时走势（腾讯）。基金暂无分时能够源，返回 available=False。"""
    asset_type = asset_type or classify_code(code)
    if asset_type == "fund":
        return {"code": code, "type": asset_type, "kind": "minute",
                "available": False, "reason": "fund_not_supported"}
    try:
        return tencent.get_minute(code, asset_type)
    except Exception as e:  # noqa
        return {"code": code, "type": asset_type, "kind": "minute",
                "available": False, "reason": str(e)}


def _stock_kline(code, asset_type, period, limit):
    if asset_type == "etf":
        df = ak.fund_etf_hist_em(symbol=code, period=period, adjust="qfq")
    else:
        df = ak.stock_zh_a_hist(symbol=code, period=period, adjust="qfq")
    if df is None or df.empty:
        return {"code": code, "type": asset_type, "rows": []}
    df = df.tail(limit)
    rows = []
    for _, r in df.iterrows():
        rows.append({
            "date": str(r.get("日期")), "open": _f(r.get("开盘")),
            "close": _f(r.get("收盘")), "high": _f(r.get("最高")),
            "low": _f(r.get("最低")), "volume": _f(r.get("成交量")),
        })
    return {"code": code, "type": asset_type, "kind": "kline", "rows": rows}


def _fund_nav_series(code, limit):
    df = ak.fund_open_fund_info_em(symbol=code, indicator="单位净值走势")
    if df is None or df.empty:
        return {"code": code, "type": "fund", "rows": []}
    df = df.tail(limit)
    rows = []
    for _, r in df.iterrows():
        rows.append({"date": str(r.get("净值日期")), "nav": _f(r.get("单位净值")),
                     "change_pct": _f(r.get("日增长率"))})
    return {"code": code, "type": "fund", "kind": "nav", "rows": rows}


# ------------------------------------------------------------------ 大盘指数
def get_index_overview():
    """主要指数概览：上证/深证/创业板。优先腾讯。"""
    cached = _cache_get("index_overview", 5)
    if cached:
        return cached
    out = []
    try:
        out = tencent.get_index_overview()
    except Exception as e:  # noqa
        print(f"[index] 腾讯指数失败，尝试 akshare: {e}")
        if ak is not None:
            targets = [("000001", "上证指数"), ("399001", "深证成指"), ("399006", "创业板指")]
            try:
                df = ak.stock_zh_index_spot_em(symbol="沪深重要指数")
                for code, name in targets:
                    row = df[df["代码"] == code]
                    if not row.empty:
                        r = row.iloc[0]
                        out.append({"code": code, "name": name,
                                    "price": _f(r.get("最新价")),
                                    "change_pct": _f(r.get("涨跌幅"))})
            except Exception as e2:  # noqa
                print(f"[index] akshare 指数也失败: {e2}")
    if out:
        _cache_set("index_overview", out)
    return out


# ------------------------------------------------------------------ 新闻
def get_news(code: str, limit: int = 8):
    """个股相关新闻（AKShare 东财个股新闻）。基金暂用其重仓无新闻，返回空。"""
    _check_ak()
    key = f"news:{code}"
    cached = _cache_get(key, _TTL_NEWS)
    if cached:
        return cached
    news = []
    try:
        df = ak.stock_news_em(symbol=code)
        if df is not None and not df.empty:
            for _, r in df.head(limit).iterrows():
                content = str(r.get("新闻内容", ""))
                news.append({
                    "title": str(r.get("新闻标题", "")),
                    "time": str(r.get("发布时间", "")),
                    "source": str(r.get("文章来源", "")),
                    "summary": content[:200],
                    "content": content,   # 全文，供前端抽屉点开查看
                })
    except Exception as e:  # noqa
        print(f"[news] 新闻获取失败: {e}")
    _cache_set(key, news)
    return news


# ------------------------------------------------------------------ 财务摘要
def get_financial(code: str):
    """个股财务摘要（AKShare stock_financial_abstract）。返回最新季度关键指标的
    数值(已折算:营收/净利→亿元, 比率类→% )、同比、以及报告期列表。带 6h 缓存。"""
    _check_ak()
    key = f"fin:{code}"
    cached = _cache_get(key, 6 * 3600)
    if cached is not None:
        return cached
    try:
        df = ak.stock_financial_abstract(symbol=code)
    except Exception as e:  # noqa
        return {"code": code, "error": str(e), "items": [], "latest_quarter": None}
    if df is None or df.empty:
        return {"code": code, "items": [], "latest_quarter": None}
    date_cols = [c for c in df.columns if c not in ("选项", "指标")]
    # 仅保留形如 20260630 的日期列，且按时间排序
    date_cols = sorted([c for c in date_cols if str(c).replace("-", "").isdigit()],
                       key=lambda x: str(x))
    if not date_cols:
        return {"code": code, "items": [], "latest_quarter": None}
    latest = date_cols[-1]
    yoy_col = date_cols[-5] if len(date_cols) >= 5 else None  # 去年同期
    pct_keys = {"roe", "gross_margin", "net_margin", "debt_ratio"}
    # (展示名, key, 优先取首个匹配)
    MAP = [
        ("营业总收入", "revenue"), ("营业收入", "revenue"),
        ("归母净利润", "net_profit"), ("净利润", "net_profit"),
        ("净资产收益率", "roe"),
        ("销售毛利率", "gross_margin"),
        ("销售净利率", "net_margin"),
        ("资产负债率", "debt_ratio"),
    ]
    seen = set()
    items = []
    name_col = "指标" if "指标" in df.columns else "选项"
    for disp, key in MAP:
        if key in seen:
            continue
        row = df[df[name_col] == disp]
        if row.empty:
            continue
        r = row.iloc[0]
        v = _f(r.get(latest))
        if v is None:
            continue
        is_pct = key in pct_keys
        yv = _f(r.get(yoy_col)) if yoy_col else None
        value = round(v / 1e8, 2) if not is_pct else round(v, 2)
        yoy = None
        if yv is not None and yv != 0:
            yoy = round((v / yv - 1) * 100, 1) if not is_pct else round(v - yv, 1)
        items.append({"key": key, "name": disp,
                      "value": value, "unit": "%" if is_pct else "亿",
                      "yoy": yoy})
        seen.add(key)
    res = {"code": code, "latest_quarter": str(latest),
           "quarters": [str(c) for c in date_cols], "items": items}
    _cache_set(key, res)
    return res


# ------------------------------------------------------------------ 行业维度（同花顺源，避开被墙的东财）
def get_industry_overview():
    """90 个申万/同花顺行业的实时概览：涨跌幅 / 净流入 / 涨跌家数 / 领涨股。
    用于「行业」页的多维度市场扫描。带 2 分钟缓存。"""
    _check_ak()
    key = "industry_overview"
    cached = _cache_get(key, 120)
    if cached is not None:
        return cached
    try:
        df = ak.stock_board_industry_summary_ths()
    except Exception as e:  # noqa
        return {"error": str(e), "items": []}
    out = []
    for _, r in df.iterrows():
        try:
            out.append({
                "name": str(r.get("板块")),
                "change_pct": _f(r.get("涨跌幅")),
                "net_inflow": _f(r.get("净流入")),        # 单位：亿元
                "volume": _f(r.get("总成交量")),
                "amount": _f(r.get("总成交额")),
                "up_count": _f(r.get("上涨家数")),
                "down_count": _f(r.get("下跌家数")),
                "avg_price": _f(r.get("均价")),
                "leader": str(r.get("领涨股")) if r.get("领涨股") else None,
                "leader_price": _f(r.get("领涨股-最新价")),
                "leader_chg": _f(r.get("领涨股-涨跌幅")),
            })
        except Exception:  # noqa
            continue
    res = {"items": out, "source": "ths"}
    _cache_set(key, res)
    return res


def get_industry_index(name: str, limit: int = 120):
    """行业指数 K线（同花顺源），用于点击行业后查看走势。"""
    _check_ak()
    key = f"ind_index:{name}:{limit}"
    cached = _cache_get(key, 1800)
    if cached is not None:
        return cached
    try:
        df = ak.stock_board_industry_index_ths(symbol=name)
    except Exception as e:  # noqa
        return {"error": str(e), "rows": []}
    df = df.tail(limit)
    rows = []
    for _, r in df.iterrows():
        rows.append({
            "date": str(r.get("日期")),
            "open": _f(r.get("开盘价")),
            "close": _f(r.get("收盘价")),
            "high": _f(r.get("最高价")),
            "low": _f(r.get("最低价")),
            "volume": _f(r.get("成交量")),
        })
    res = {"name": name, "kind": "kline", "rows": rows, "source": "ths"}
    _cache_set(key, res)
    return res


# ------------------------------------------------------------------ 估值分位（历史时序）
def _percentile(sorted_vals, q):
    """q: 0-100，返回分位数。sorted_vals 升序。"""
    if not sorted_vals:
        return None
    n = len(sorted_vals)
    if n == 1:
        return sorted_vals[0]
    idx = (n - 1) * (q / 100.0)
    lo = int(idx)
    hi = min(lo + 1, n - 1)
    frac = idx - lo
    return sorted_vals[lo] + (sorted_vals[hi] - sorted_vals[lo]) * frac


def get_valuation_history(code: str = None, years: int = 10):
    """全市场 PB 历史分位时序（同花顺 stock_a_all_pb，约 5200 交易日）。
    返回市场 PB 近 N 年曲线 + 当前分位 + 分位带(25/50/75)；若给出 code，
    附带该股在『全A快照』中的截面 PE/PB 分位（同行比较）。"""
    _check_ak()
    key = f"valhist:{years}"
    cached = _cache_get(key, 3600)
    if cached is None:
        try:
            df = ak.stock_a_all_pb()
            df = df[df["middlePB"].notna()]
            # 取近 N 年
            df = df.tail(years * 252 + 30)
            series = []
            for _, r in df.iterrows():
                d = r.get("date")
                pb = _f(r.get("middlePB"))
                if d is None or pb is None:
                    continue
                series.append({"date": str(d)[:10], "pb": round(pb, 3)})
            vals = [s["pb"] for s in series]
            svals = sorted(vals)
            cur = vals[-1] if vals else None
            below = sum(1 for x in svals if x <= (cur or 0))
            pct_now = round(below / len(svals) * 100, 1) if svals else None
            cached = {
                "series": series,
                "current": {"pb": cur, "percentile": pct_now},
                "stats": {
                    "min": round(min(svals), 3) if svals else None,
                    "max": round(max(svals), 3) if svals else None,
                    "p25": round(_percentile(svals, 25), 3) if svals else None,
                    "p50": round(_percentile(svals, 50), 3) if svals else None,
                    "p75": round(_percentile(svals, 75), 3) if svals else None,
                },
                "source": "ths",
            }
            _cache_set(key, cached)
        except Exception as e:  # noqa
            cached = {"error": str(e), "series": []}
            _cache_set(key, cached)
    res = dict(cached)
    # 附带个股截面分位（来自全A快照）
    if code:
        try:
            from backend import universe
            snap = universe.get_spot_snapshot() or []
            pe_pool = sorted(s["pe"] for s in snap if (s.get("pe") or 0) > 0)
            pb_pool = sorted(s["pb"] for s in snap if (s.get("pb") or 0) > 0)
            cur = next((s for s in snap if s["code"] == code), None)
            def pct(pool, x):
                if not pool or x is None or x <= 0:
                    return None
                below = sum(1 for v in pool if v <= x)
                return round(below / len(pool) * 100, 1)
            res["stock"] = {
                "pe": cur.get("pe") if cur else None,
                "pb": cur.get("pb") if cur else None,
                "pe_quantile": pct(pe_pool, cur.get("pe") if cur else None),
                "pb_quantile": pct(pb_pool, cur.get("pb") if cur else None),
                "sample": len(snap),
            }
        except Exception:  # noqa
            res["stock"] = None
    return res


# ------------------------------------------------------------------ 辅助
def _f(v):
    """安全转 float。"""
    try:
        if v is None or (isinstance(v, float) and pd.isna(v)):
            return None
        if isinstance(v, str) and v.strip() in ("", "-", "--"):
            return None
        return float(v)
    except Exception:  # noqa
        return None


def health():
    return {"akshare_ready": ak is not None, "import_error": _AK_IMPORT_ERROR,
            "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
