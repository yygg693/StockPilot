"""Dependency injection: shared singletons via FastAPI Depends."""
from __future__ import annotations

from fastapi import Request

from backend.app.core.cache import TTLCache
from backend.app.core.config import Settings, get_settings
from backend.app.core.exceptions import AuthError
from backend.app.core.security import decode_access_token, extract_token_from_header

# Global async cache instance (shared across routers)
_cache: TTLCache | None = None


def get_cache() -> TTLCache:
    global _cache
    if _cache is None:
        s = get_settings()
        _cache = TTLCache(default_ttl=s.cache.quote_ttl, max_size=2048)
    return _cache


def get_config() -> Settings:
    return get_settings()


async def get_current_user(request: Request) -> dict:
    """FastAPI dependency: extract and validate current user from JWT token.

    When auth_enabled is False (development mode), returns an anonymous user
    without requiring a token. This allows gradual rollout of authentication.
    """
    settings = get_settings()

    # Development mode: auth disabled, return anonymous user
    if not settings.security.auth_enabled:
        return {"user_id": 0, "username": "anonymous", "role": "admin"}

    # Production mode: require valid JWT token
    token = extract_token_from_header(request.headers.get("authorization"))
    if not token:
        raise AuthError("未提供认证令牌，请先登录")

    payload = decode_access_token(token)
    if not payload:
        raise AuthError("认证令牌无效或已过期，请重新登录")

    return {
        "user_id": int(payload["sub"]),
        "username": payload["username"],
        "role": payload["role"],
    }


async def get_optional_user(request: Request) -> dict | None:
    """FastAPI dependency: extract current user if token present, else None.

    Used for endpoints that work with or without authentication (e.g., public
    data endpoints that personalize when logged in).
    """
    settings = get_settings()
    if not settings.security.auth_enabled:
        return {"user_id": 0, "username": "anonymous", "role": "admin"}

    token = extract_token_from_header(request.headers.get("authorization"))
    if not token:
        return None

    payload = decode_access_token(token)
    if not payload:
        return None

    return {
        "user_id": int(payload["sub"]),
        "username": payload["username"],
        "role": payload["role"],
    }
