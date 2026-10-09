"""FastAPI application factory with lifespan."""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from backend.app.core.config import DATA_DIR, DB_PATH, FRONTEND_DIR, get_settings
from backend.app.core.exceptions import AppException, app_exception_handler
from backend.app.core.http_client import close_http_client, init_http_client
from backend.app.core.logging import get_logger, setup_logging
from backend.app.db.session import close_db, init_db

logger = get_logger("stockpilot")


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    setup_logging(debug=settings.debug)
    if not settings.security.auth_enabled:
        logger.warning(
            "security.auth_disabled",
            msg="认证已禁用(auth_enabled=false)，仅限本地/内网使用；公开部署前请设为 true 并配置强 jwt_secret",
        )
    elif len(settings.security.jwt_secret) < 32:
        logger.warning("security.weak_jwt_secret", msg="jwt_secret 长度不足 32 位，存在安全风险")
    logger.info("stockpilot.starting", version="2.0.0", debug=settings.debug)

    # Ensure data dir
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    # Init async HTTP client with connection pooling
    await init_http_client()

    # Database: ensure schema & tables exist at startup.
    # init_db() runs idempotent CREATE TABLE IF NOT EXISTS, so the app is
    # ready to serve DB-backed routes immediately (no lazy first-request race).
    await init_db()
    logger.info("stockpilot.db_ready", db=str(DB_PATH))

    logger.info("stockpilot.ready")
    yield

    # Shutdown
    await close_http_client()
    await close_db()
    logger.info("stockpilot.shutdown")


def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(
        title="StockPilot API",
        description=(
            "AI 驱动的个人股票投资助手后端 API。\n\n"
            "## 功能模块\n"
            "- **认证**：用户注册/登录，JWT 令牌\n"
            "- **行情**：实时行情、K 线、资金流\n"
            "- **选股**：多维筛选、板块轮动\n"
            "- **回测**：含交易成本的专业回测引擎\n"
            "- **交易**：模拟交易 + AI 自动交易提案确认\n"
            "- **AI**：DeepSeek 驱动的投资分析与决策\n"
            "- **风控**：适当性管理、风险预警、审计日志\n"
        ),
        version="2.0.0",
        contact={"name": "StockPilot", "url": "https://github.com/StockPilot"},
        license_info={"name": "MIT"},
        openapi_tags=[
            {"name": "auth", "description": "用户认证与授权"},
            {"name": "system", "description": "系统健康检查与配置"},
            {"name": "quote", "description": "实时行情与历史 K 线"},
            {"name": "screener", "description": "选股筛选器"},
            {"name": "backtest", "description": "策略回测引擎"},
            {"name": "trade", "description": "模拟交易与 AI 交易提案"},
            {"name": "ai", "description": "AI 投资分析与自动决策"},
            {"name": "fund", "description": "资金流向分析"},
            {"name": "sector", "description": "板块行情与轮动"},
            {"name": "report", "description": "投资报告生成"},
            {"name": "portfolio", "description": "持仓组合管理"},
            {"name": "suitability", "description": "投资者适当性管理"},
        ],
        lifespan=lifespan,
    )

    # CORS - restricted to configured origins (no more wildcard)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.security.cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "X-API-Key"],
    )

    # Rate limiting
    from backend.app.core.rate_limit import RateLimitMiddleware
    app.add_middleware(
        RateLimitMiddleware,
        general_limit=settings.security.rate_limit_per_minute,
        ai_limit=settings.security.ai_rate_limit_per_minute,
    )

    # Exception handlers
    app.add_exception_handler(AppException, app_exception_handler)

    # Catch-all handler: log full traceback for unhandled exceptions
    import logging as _logging
    _err_logger = _logging.getLogger("stockpilot.errors")

    async def _unhandled_exception_handler(request: Request, exc: Exception):
        import traceback as _tb
        tb_str = _tb.format_exc()
        _err_logger.error("unhandled_exception", exc_info=True, extra={
            "path": request.url.path, "method": request.method,
        })
        return JSONResponse(
            status_code=500,
            content={"error": "INTERNAL_ERROR", "message": str(exc), "traceback": tb_str},
        )

    app.add_exception_handler(Exception, _unhandled_exception_handler)

    # API Key middleware
    _register_api_key_guard(app, settings)

    # Routers
    _register_routers(app)

    # Static frontend (production)
    if FRONTEND_DIR.exists():
        app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")

    return app


def _register_api_key_guard(app: FastAPI, settings) -> None:
    api_key = settings.server.api_key.strip()
    if not api_key:
        return

    from starlette.middleware.base import BaseHTTPMiddleware

    class APIKeyMiddleware(BaseHTTPMiddleware):
        async def dispatch(self, request: Request, call_next):
            path = request.url.path
            if path.startswith("/api/") and path != "/api/health":
                provided = request.headers.get("x-api-key", "")
                if provided != api_key:
                    return JSONResponse(
                        status_code=401,
                        content={"error": "AUTH_ERROR", "message": "Invalid or missing API key"},
                    )
            return await call_next(request)

    app.add_middleware(APIKeyMiddleware)


def _register_routers(app: FastAPI) -> None:
    from backend.app.routers import (
        ai,
        auth,
        backtest,
        fund,
        portfolio,
        quote,
        report,
        screener,
        sector,
        suitability,
        system,
        trade,
    )

    app.include_router(auth.router, prefix="/api", tags=["auth"])
    app.include_router(system.router, prefix="/api", tags=["system"])
    app.include_router(quote.router, prefix="/api", tags=["quote"])
    app.include_router(screener.router, prefix="/api", tags=["screener"])
    app.include_router(backtest.router, prefix="/api", tags=["backtest"])
    app.include_router(trade.router, prefix="/api", tags=["trade"])
    app.include_router(ai.router, prefix="/api", tags=["ai"])
    app.include_router(fund.router, prefix="/api", tags=["fund"])
    app.include_router(sector.router, prefix="/api", tags=["sector"])
    app.include_router(report.router, prefix="/api", tags=["report"])
    app.include_router(portfolio.router, prefix="/api", tags=["portfolio"])
    app.include_router(suitability.router, prefix="/api", tags=["suitability"])


# Convenience: uvicorn backend.app.main:app
app = create_app()
