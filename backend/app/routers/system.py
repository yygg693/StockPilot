"""System routes: health, config, universe build status."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from backend.app.core.audit import extract_request_info, get_audit_logs, log_audit
from backend.app.core.config import get_settings
from backend.app.deps import get_current_user

router = APIRouter()

# Market connectivity check cache (avoid external call on every health poll)
_market_check: dict = {"status": None, "ts": 0.0}
_MARKET_CHECK_TTL = 30.0  # seconds


async def _check_market() -> str:
    import time as _time

    from backend.app.core.http_client import get_http_client
    now = _time.time()
    if _market_check["status"] and now - _market_check["ts"] < _MARKET_CHECK_TTL:
        return _market_check["status"]
    client = get_http_client()
    try:
        r = await client.get(
            "https://qt.gtimg.cn/q=sh000001",
            headers={"Referer": "https://finance.qq.com"},
            timeout=5.0,
        )
        status = "online" if r.status_code == 200 else "offline"
    except Exception:
        status = "offline"
    _market_check["status"] = status
    _market_check["ts"] = now
    return status


@router.get("/health")
async def health():
    """Enhanced health check: market connectivity + DB + AI config."""
    checks = {}

    # 1. Market API connectivity (cached 30s)
    checks["market"] = await _check_market()

    # 2. Database connectivity
    try:
        from backend.app.db.session import get_db
        db = await get_db()
        cursor = await db.execute("SELECT 1")
        await cursor.fetchone()
        checks["database"] = "ok"
    except Exception:
        checks["database"] = "error"

    # 3. AI configuration
    settings = get_settings()
    checks["ai_configured"] = settings.ai.configured

    # Overall status
    all_ok = checks["market"] == "online" and checks["database"] == "ok"
    return {
        "status": "ok" if all_ok else "degraded",
        "version": "2.0.0",
        "checks": checks,
    }


@router.get("/config/ai")
async def get_ai_config(_user: dict = Depends(get_current_user)):
    settings = get_settings()
    key = settings.ai.api_key.strip()
    return {
        "data": {
            "api_key": ("****" + key[-4:]) if len(key) >= 4 else ("set" if key else ""),
            "api_key_set": bool(key),
            "base_url": settings.ai.base_url,
            "model": settings.ai.model,
            "enabled": settings.ai.enabled,
        }
    }




@router.post("/config/ai/test")
async def test_ai_connection(body: dict, _user: dict = Depends(get_current_user)):
    """Test AI API connection with provided credentials."""
    import httpx
    api_key = body.get("api_key", "").strip()
    base_url = body.get("base_url", "https://api.deepseek.com").strip().rstrip("/")
    model = body.get("model", "deepseek-chat").strip()

    if not api_key:
        return {"data": {"success": False, "message": "API Key 不能为空"}}

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            r = await client.post(
                f"{base_url}/chat/completions",
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json={
                    "model": model,
                    "messages": [{"role": "user", "content": "Hi"}],
                    "max_tokens": 5,
                },
            )
            if r.status_code == 200:
                return {"data": {"success": True, "message": "连接成功"}}
            else:
                detail = r.json().get("error", {}).get("message", str(r.status_code)) if r.headers.get("content-type", "").startswith("application/json") else str(r.status_code)
                return {"data": {"success": False, "message": f"连接失败: {detail}"}}
    except httpx.TimeoutException:
        return {"data": {"success": False, "message": "连接超时，请检查网络或Base URL"}}
    except Exception as e:
        return {"data": {"success": False, "message": f"连接失败: {str(e)[:100]}"}}


@router.post("/config/ai/save")
async def save_ai_config(body: dict, request: Request, _user: dict = Depends(get_current_user)):
    """Persist AI config to data/ai_config.json and update the runtime settings.

    This is what makes a key saved from the settings page actually usable by the
    backend AI analysis endpoints (which read from get_settings().ai)."""
    from backend.app.core import config as config_module

    settings = get_settings()

    api_key = (body.get("api_key") or "").strip()
    base_url = (body.get("base_url") or "https://api.deepseek.com").strip().rstrip("/")
    model = (body.get("model") or "deepseek-chat").strip()
    enabled = body.get("enabled", settings.ai.enabled)
    if isinstance(enabled, str):
        enabled = enabled.lower() not in ("0", "false", "no", "")
    enabled = bool(enabled)

    # 1) Persist non-secret fields to disk (api_key is never written to disk;
    #    it lives in the STOCKPILOT_AI_API_KEY env var or runtime memory).
    config_module.save_ai_config_to_disk("", base_url, model, enabled)

    # 2) Update the cached runtime Settings singleton so the change takes
    #    effect immediately without a restart.
    settings.ai.api_key = api_key
    settings.ai.base_url = base_url
    settings.ai.model = model
    settings.ai.enabled = enabled

    # Audit log
    info = extract_request_info(request)
    await log_audit(
        action="config.ai.save",
        target="ai_config",
        detail={"base_url": base_url, "model": model, "enabled": enabled, "api_key_set": bool(api_key)},
        **info,
    )

    return {"data": {
        "success": True,
        "message": "配置已保存",
        "api_key_set": bool(api_key),
        "base_url": base_url,
        "model": model,
        "enabled": enabled,
    }}


@router.get("/audit/logs")
async def audit_logs(
    limit: int = 100,
    offset: int = 0,
    action: str = "",
    _user: dict = Depends(get_current_user),
):
    """Query audit logs (newest first). Optional action prefix filter."""
    logs = await get_audit_logs(limit=limit, offset=offset, action_filter=action)
    return {"data": logs}


@router.get("/config/ai/models")
async def list_ai_models(_user: dict = Depends(get_current_user)):
    """Fetch available models from the AI provider using saved config."""
    settings = get_settings()
    if not settings.ai.api_key:
        return {"data": {"models": [], "error": "No API key configured"}}

    from backend.app.core.http_client import get_http_client
    client = get_http_client()
    try:
        r = await client.get(
            f"{settings.ai.base_url}/models",
            headers={"Authorization": f"Bearer {settings.ai.api_key}"},
            timeout=15.0,
        )
        r.raise_for_status()
        data = r.json()
        models = [m["id"] for m in data.get("data", []) if m.get("id")]
        models.sort()
        return {"data": {"models": models, "error": None}}
    except Exception as e:
        return {"data": {"models": [], "error": str(e)}}


@router.get("/universe/status")
async def universe_status():
    # TODO: migrate from old universe.py build status
    return {"data": {"running": False, "total": 0, "done": 0}}
