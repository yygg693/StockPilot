"""
StockPilot 后端主入口（FastAPI）。
运行：python -m uvicorn backend.main:app --reload  或直接 python backend/main.py
"""
import os
import sys

# 保证以项目根目录为基准导入 backend 包
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from fastapi import FastAPI, Query, Request  # noqa: E402
from fastapi.responses import FileResponse, JSONResponse  # noqa: E402
from fastapi.staticfiles import StaticFiles  # noqa: E402

from backend.config import CONFIG, FRONTEND_DIR, get_ai_config_masked, save_ai_config  # noqa: E402
from backend.data import market  # noqa: E402
from backend.indicators import mytt  # noqa: E402
from backend.ai import analyst  # noqa: E402
from backend import report  # noqa: E402
from backend.db import store  # noqa: E402
from backend import screener, backtest, trade  # noqa: E402
from backend import fund_screener  # noqa: E402

app = FastAPI(title="StockPilot", description="个人 AI 投资助手", version="1.0")

store.init_db()

# --------------------------------------------------------------- API Key 认证
_API_KEY = os.environ.get("STOCKPILOT_API_KEY", "").strip()


@app.middleware("http")
async def api_key_guard(request: Request, call_next):
    """简易 API Key 认证。设置环境变量 STOCKPILOT_API_KEY 后启用，未设置则跳过（本地开发）。"""
    if _API_KEY:
        path = request.url.path
        # 仅保护 /api/ 路由，放行 health（用于监控）和静态资源/前端页面
        if path.startswith("/api/") and path != "/api/health":
            provided = request.headers.get("x-api-key", "")
            if provided != _API_KEY:
                return JSONResponse(status_code=401, content={"detail": "Invalid or missing API key"})
    return await call_next(request)


# --------------------------------------------------------------- API
@app.get("/api/health")
def health():
    return {"status": "ok", "market": market.health(),
            "ai_configured": bool((CONFIG.get("ai", {}).get("api_key") or "").strip())}


@app.get("/api/index")
def index_overview():
    return {"data": market.get_index_overview()}


@app.get("/api/breadth")
def breadth():
    """市场宽度（基于全A快照）：涨/跌/平家数、涨停/跌停、平均涨幅。"""
    from backend.universe import get_breadth
    return {"data": get_breadth()}


@app.get("/api/search")
def search(q: str = Query(..., min_length=1)):
    return {"data": market.search(q)}


@app.get("/api/watchlist")
def get_watchlist(with_quote: bool = True):
    items = store.list_watch()
    if with_quote:
        for it in items:
            try:
                qt = market.get_quote(it["code"], it["type"])
                it["price"] = qt.get("price")
                it["change_pct"] = qt.get("change_pct")
            except Exception as e:  # noqa
                it["error"] = str(e)
    return {"data": items}


@app.post("/api/watchlist/add")
def add_watch(code: str, name: str = "", type: str = "stock", grp: str = "默认"):
    if not name:
        try:
            name = market.get_quote(code, type).get("name") or code
        except Exception:  # noqa
            name = code
    store.add_watch(code, name, type, grp)
    return {"ok": True}


@app.post("/api/watchlist/remove")
def remove_watch(code: str, type: str = "stock"):
    store.remove_watch(code, type)
    return {"ok": True}


def _valuation(code: str):
    """基于全A快照，算该股票 PE/PB 在全市场有效样本中的分位数与市场中位数。
    一眼看出'贵不贵'。快照缺失时优雅降级。"""
    try:
        from backend import universe
        snap = universe.get_spot_snapshot() or []
        if not snap:
            return {"available": False}
        pe_pool = sorted(s["pe"] for s in snap if (s.get("pe") or 0) > 0)
        pb_pool = sorted(s["pb"] for s in snap if (s.get("pb") or 0) > 0)
        cur = next((s for s in snap if s["code"] == code), None)

        def pct(pool, x):
            if not pool or x is None or x <= 0:
                return None
            below = sum(1 for v in pool if v <= x)
            return round(below / len(pool) * 100, 1)

        return {
            "available": True,
            "pe_quantile": pct(pe_pool, cur.get("pe") if cur else None),
            "pb_quantile": pct(pb_pool, cur.get("pb") if cur else None),
            "pe_market_median": round(pe_pool[len(pe_pool) // 2], 2) if pe_pool else None,
            "pb_market_median": round(pb_pool[len(pb_pool) // 2], 2) if pb_pool else None,
            "sample": len(snap),
        }
    except Exception as e:  # noqa
        return {"available": False, "error": str(e)}


@app.get("/api/quote")
def quote(code: str, type: str = None):
    q = market.get_quote(code, type)
    q["valuation"] = _valuation(code)
    return {"data": q}


@app.get("/api/financial")
def financial(code: str):
    """个股财务摘要（季度营收/净利/ROE/毛利率等 + 同比）。"""
    return {"data": market.get_financial(code)}


@app.get("/api/industry/overview")
def industry_overview():
    """行业概览：90 个行业的涨跌幅/净流入/涨跌家数/领涨股（同花顺源）。"""
    return {"data": market.get_industry_overview()}


@app.get("/api/industry/index")
def industry_index(name: str, limit: int = 120):
    """行业指数 K线（同花顺源）。"""
    return {"data": market.get_industry_index(name, limit=limit)}


@app.get("/api/valuation-history")
def valuation_history(code: str = None, years: int = 10):
    """全市场 PB 历史估值分位（时序线图），可选附带个股截面分位。"""
    return {"data": market.get_valuation_history(code=code, years=years)}


@app.get("/api/kline")
def kline(code: str, type: str = None, limit: int = 120):
    return {"data": market.get_kline(code, type, limit=limit)}


@app.get("/api/minute")
def minute(code: str, type: str = None):
    """分时/日内实时走势（腾讯）：当日逐分钟点 + 均价 + 昨收，前端轮询即'活图'。"""
    return {"data": market.get_minute(code, type)}


@app.get("/api/news")
def news(code: str):
    return {"data": market.get_news(code)}


@app.get("/api/analyze")
def analyze(code: str, type: str = None):
    """核心接口：拉行情+K线+新闻 -> 指标 -> AI 决策卡片。"""
    asset_type = type or market.classify_code(code)
    quote_data = market.get_quote(code, asset_type)
    kline_data = market.get_kline(code, asset_type, limit=120)
    rows = kline_data.get("rows", [])
    # 基金净值序列转成 close 供指标计算
    if asset_type == "fund":
        norm = [{"close": r.get("nav"), "high": r.get("nav"), "low": r.get("nav")}
                for r in rows if r.get("nav") is not None]
        indicators = mytt.compute_all(norm) if len(norm) >= 20 else {"latest": {}, "signals": []}
    else:
        indicators = mytt.compute_all(rows)
    news_data = market.get_news(code) if asset_type != "fund" else []
    card = analyst.analyze(quote_data, indicators, news_data)
    return {"data": {"quote": quote_data, "indicators": indicators,
                     "news": news_data, "card": card}}


@app.get("/api/analyze/multi")
def analyze_multi(code: str, type: str = None):
    """多角色 AI 决策卡片：技术派 / 价值派 / 风控派 / 激进派。"""
    asset_type = type or market.classify_code(code)
    quote_data = market.get_quote(code, asset_type)
    kline_data = market.get_kline(code, asset_type, limit=120)
    rows = kline_data.get("rows", [])
    if asset_type == "fund":
        norm = [{"close": r.get("nav"), "high": r.get("nav"), "low": r.get("nav")}
                for r in rows if r.get("nav") is not None]
        indicators = mytt.compute_all(norm) if len(norm) >= 20 else {"latest": {}, "signals": []}
    else:
        indicators = mytt.compute_all(rows)
    news_data = market.get_news(code) if asset_type != "fund" else []
    multi = analyst.analyze_multi(quote_data, indicators, news_data)
    return {"data": {"quote": quote_data, "indicators": indicators,
                     "news": news_data, "multi": multi}}


@app.get("/api/daily-report")
def daily_report():
    """自动日报：大盘 + 自选多角色快照 + 风险清单。"""
    return {"data": report.build_daily_report()}


# --------------------------------------------------------------- Phase 3: 选股
@app.get("/api/screener")
def api_screener(strategy: str = "value", universe: str = "all",
                 pe_max: float = 20, pb_max: float = 3,
                 top_n: int = 80, limit: int = 50):
    """选股：strategy=value/momentum/golden；universe=watch/hs300/all。"""
    params = {"pe_max": pe_max, "pb_max": pb_max, "top_n": top_n, "limit": limit}
    return {"data": screener.screen(strategy=strategy, universe=universe, params=params)}


@app.get("/api/universe/status")
def api_universe_status():
    """返回股票池快照状态（数量/生成时间）+ 后台构建进度。"""
    from backend.universe import (_load_json, _SNAP_PATH, _CODES_PATH,
                                  get_all_codes, get_build_status)
    snap = _load_json(_SNAP_PATH)
    codes = _load_json(_CODES_PATH)
    # 代码清单数量（避免阻塞：直接读缓存，不触发远程拉取）
    if not codes:
        try:
            codes = {"data": get_all_codes()}
        except Exception:  # noqa
            codes = {"data": []}
    return {"data": {
        "snapshot_count": len(snap["data"]) if snap else 0,
        "snapshot_ts": snap.get("_ts") if snap else None,
        "codes_count": len(codes["data"]) if codes else 0,
        "codes_ts": codes.get("_ts") if codes else None,
        "build": get_build_status(),
    }}


@app.post("/api/universe/refresh")
def api_universe_refresh():
    """强制后台重建全市场快照（基于代码清单 + 腾讯批量行情）。
    非阻塞：立即返回，前端轮询 /api/universe/status 的 build 进度。"""
    from backend.universe import get_all_codes, build_snapshot_async
    get_all_codes(force=True)
    ok = build_snapshot_async()
    return {"ok": ok, "msg": "后台构建已启动，请轮询 /api/universe/status 的 build 字段"}


# --------------------------------------------------------------- Phase 4: 选基金
@app.get("/api/fund-screener")
def api_fund_screener(strategy: str = "etf_momentum", top_n: int = 30):
    """智能选基金：strategy=etf_momentum/etf_active/open_year/open_3y/open_steady。"""
    return {"data": fund_screener.screen(strategy=strategy, params={"top_n": top_n})}


# --------------------------------------------------------------- Phase 3: 回测
@app.get("/api/backtest")
def api_backtest(code: str, strategy: str = "ma_cross", type: str = None,
                 fast: int = 5, slow: int = 20, limit: int = 250):
    """回测：strategy=ma_cross/macd。ma_cross 用 fast/slow 双均线。"""
    params = {"fast": fast, "slow": slow}
    return {"data": backtest.backtest(code, strategy=strategy, params=params,
                                      limit=limit, asset_type=type)}


# --------------------------------------------------------------- Phase 3: 模拟盘
@app.get("/api/trade/positions")
def api_positions():
    """模拟盘持仓 + 实时盈亏。"""
    return {"data": trade.positions_with_pnl()}


@app.post("/api/trade/buy")
def api_buy(code: str, qty: float, name: str = "", type: str = None,
            price: float = None):
    return {"data": trade.buy(code, qty, name=name or None, asset_type=type, price=price)}


@app.post("/api/trade/sell")
def api_sell(code: str, qty: float, type: str = None, price: float = None):
    return {"data": trade.sell(code, qty, asset_type=type, price=price)}


# --------------------------------------------------------------- 前端静态
@app.get("/api/config")
def get_config():
    """返回当前 AI 配置（api_key 已掩码，不暴露明文）。"""
    from backend.config import get_ai_config_masked
    return {"data": get_ai_config_masked()}


@app.post("/api/config")
def post_config(payload: dict = None):
    """保存 AI 配置（api_key / base_url / model / enabled），写回 config.yaml 并热更新内存。"""
    if not isinstance(payload, dict):
        payload = {}
    save_ai_config(payload)
    return {"ok": True, "data": get_ai_config_masked()}


@app.get("/")
def home():
    index_html = os.path.join(FRONTEND_DIR, "index.html")
    if os.path.exists(index_html):
        return FileResponse(index_html)
    return JSONResponse({"msg": "前端未就绪，请检查 frontend/index.html"})


if os.path.isdir(FRONTEND_DIR):
    app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")


if __name__ == "__main__":
    import uvicorn
    srv = CONFIG.get("server", {})
    uvicorn.run("backend.main:app", host=srv.get("host", "127.0.0.1"),
                port=srv.get("port", 8000), reload=False)
