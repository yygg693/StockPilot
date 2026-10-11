"""Simple in-memory rate limiter middleware (no external dependencies).

Uses a sliding window per client IP. Two tiers:
- General API: rate_limit_per_minute (default 60)
- AI endpoints: ai_rate_limit_per_minute (default 20, stricter)
"""
from __future__ import annotations

import time
from collections import defaultdict
from collections.abc import Awaitable, Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response


_LOOPBACK = {"127.0.0.1", "::1", "localhost", "0:0:0:0:0:0:0:1"}


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Per-IP sliding-window rate limiter.

    AI endpoints (paths starting with /api/ai/) get a stricter limit.

    NOTE: StockPilot is a single-user desktop app that only ever listens on
    localhost. Rate-limiting loopback requests is pure self-harm (the user's
    own chat/market-summary calls would get 429'd after a handful of requests),
    so loopback clients are exempt. The limiter still protects the app if it is
    ever exposed to a real network interface.
    """

    def __init__(self, app, general_limit: int = 120, ai_limit: int = 60):
        super().__init__(app)
        self.general_limit = general_limit
        self.ai_limit = ai_limit
        # _windows[ip] = list of timestamps
        self._windows: dict[str, list[float]] = defaultdict(list)

    def _get_limit(self, path: str) -> int:
        if path.startswith("/api/ai/"):
            return self.ai_limit
        return self.general_limit

    def _check(self, ip: str, limit: int) -> bool:
        """Return True if allowed, False if rate limited."""
        now = time.monotonic()
        window = self._windows[ip]
        # Prune entries older than 60 seconds
        cutoff = now - 60.0
        while window and window[0] < cutoff:
            window.pop(0)
        if len(window) >= limit:
            return False
        window.append(now)
        return True

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        path = request.url.path

        # Only rate-limit API endpoints
        if not path.startswith("/api/"):
            return await call_next(request)

        # Get client IP (respect proxy headers)
        client_ip = request.headers.get("x-forwarded-for", "").split(",")[0].strip()
        if not client_ip:
            client_ip = request.client.host if request.client else "unknown"

        # Loopback (desktop single-user) is exempt from rate limiting.
        if client_ip in _LOOPBACK:
            return await call_next(request)

        limit = self._get_limit(path)
        if not self._check(client_ip, limit):
            return JSONResponse(
                status_code=429,
                content={
                    "error": "RATE_LIMITED",
                    "message": f"请求过于频繁，请稍后再试（限制: {limit}次/分钟）",
                },
                headers={"Retry-After": "60"},
            )

        return await call_next(request)
