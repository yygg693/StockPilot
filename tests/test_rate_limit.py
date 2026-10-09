"""Tests for backend.app.core.rate_limit — sliding window rate limiter."""
from __future__ import annotations

import time

from backend.app.core.rate_limit import RateLimitMiddleware


class TestRateLimitCheck:
    def test_under_limit_allowed(self):
        """The internal _check method should allow requests under the limit."""
        from starlette.applications import Starlette

        app = Starlette()
        mw = RateLimitMiddleware(app, general_limit=5, ai_limit=2)
        for _ in range(4):
            assert mw._check("1.2.3.4", 5) is True

    def test_at_limit_blocked(self):
        from starlette.applications import Starlette

        app = Starlette()
        mw = RateLimitMiddleware(app, general_limit=3, ai_limit=2)
        for _ in range(3):
            mw._check("1.2.3.4", 3)
        assert mw._check("1.2.3.4", 3) is False

    def test_different_ips_independent(self):
        from starlette.applications import Starlette

        app = Starlette()
        mw = RateLimitMiddleware(app, general_limit=2, ai_limit=1)
        mw._check("1.1.1.1", 2)
        mw._check("1.1.1.1", 2)
        # IP 2 should still be allowed
        assert mw._check("2.2.2.2", 2) is True

    def test_ai_path_gets_stricter_limit(self):
        from starlette.applications import Starlette

        app = Starlette()
        mw = RateLimitMiddleware(app, general_limit=10, ai_limit=2)
        assert mw._get_limit("/api/quote/list") == 10
        assert mw._get_limit("/api/ai/chat") == 2

    def test_non_api_path_not_limited(self):
        from starlette.applications import Starlette

        app = Starlette()
        mw = RateLimitMiddleware(app, general_limit=10, ai_limit=1)
        # Non-API paths get general limit (dispatch skips them, but _get_limit still returns it)
        assert mw._get_limit("/static/index.html") == 10
