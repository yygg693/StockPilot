"""Shared async HTTP client with connection pooling.

Extracted from main.py to break circular imports:
main.py -> routers -> services -> main.py (get_http_client)

Now: main.py -> core.http_client <- routers/services
"""
from __future__ import annotations

import httpx

# Shared httpx client (created in lifespan, lazy-init for testing)
_http_client: httpx.AsyncClient | None = None


def get_http_client() -> httpx.AsyncClient:
    """Return the shared async HTTP client, lazy-init if needed."""
    global _http_client
    if _http_client is None:
        _http_client = httpx.AsyncClient(
            timeout=httpx.Timeout(15.0, connect=5.0),
            limits=httpx.Limits(max_connections=100, max_keepalive_connections=20),
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"},
            follow_redirects=True,
        )
    return _http_client


async def init_http_client() -> None:
    """Create the client with explicit settings (called from lifespan)."""
    global _http_client
    _http_client = httpx.AsyncClient(
        timeout=httpx.Timeout(15.0, connect=5.0),
        limits=httpx.Limits(max_connections=100, max_keepalive_connections=20),
        headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"},
        follow_redirects=True,
    )


async def close_http_client() -> None:
    """Close and reset the client (called from lifespan shutdown)."""
    global _http_client
    if _http_client is not None:
        await _http_client.aclose()
        _http_client = None
