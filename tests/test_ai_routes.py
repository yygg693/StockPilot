"""AI route tests for StockPilot backend.

Verifies the AI analysis route end-to-end WITHOUT depending on a live
DeepSeek key, the openai SDK version, OR the real on-disk database:

- The active AI routes call DeepSeek via the shared httpx client
  (backend.app.core.http_client.get_http_client), NOT the openai SDK.
  This test pins that contract by mocking the http client so the route
  logic (request build -> response parse -> markdown cleanup -> error
  wrapping) is exercised independently of network/credit/SDK-version/DB.

- init_db() in the lifespan is mocked out: /api/ai/analyze never touches
  the database, so we avoid writing to the real stockpilot_v2.db (which a
  running dev server may hold) and keep the test hermetic.

Run with: pytest tests/test_ai_routes.py -v -p no:cacheprovider
"""
from __future__ import annotations

import os
from unittest.mock import AsyncMock, MagicMock

import pytest
from starlette.testclient import TestClient

# Only env vars that the pydantic settings actually read.
os.environ.setdefault("STOCKPILOT_SECURITY_AUTH_ENABLED", "false")
os.environ.setdefault("STOCKPILOT_AI_API_KEY", "test-key")
os.environ.setdefault("STOCKPILOT_AI_BASE_URL", "https://api.deepseek.com")
os.environ.setdefault("STOCKPILOT_AI_MODEL", "deepseek-chat")


@pytest.fixture
def client(monkeypatch):
    # Make the lifespan NOT write to the real DB (analyze never uses it).
    import backend.app.main as main_mod

    monkeypatch.setattr(main_mod, "init_db", AsyncMock())
    monkeypatch.setattr(main_mod, "close_db", AsyncMock())

    # Build a fake httpx client whose .post() returns a well-formed
    # DeepSeek chat/completions response.
    fake_resp = MagicMock()
    fake_resp.raise_for_status = MagicMock()
    fake_resp.json = MagicMock(
        return_value={
            "choices": [
                {
                    "message": {
                        "content": "## 基本面\n贵州茅台业绩稳健。*技术面*看好，建议持有。"
                    }
                }
            ]
        }
    )
    fake_http_client = MagicMock()
    fake_http_client.post = AsyncMock(return_value=fake_resp)

    import backend.app.routers.ai as ai_router
    import backend.app.core.http_client as http_client_mod

    monkeypatch.setattr(ai_router, "get_http_client", lambda: fake_http_client)
    monkeypatch.setattr(http_client_mod, "get_http_client", lambda: fake_http_client)

    from backend.app.main import create_app

    app = create_app()
    with TestClient(app) as c:
        yield c


def test_ai_analyze_returns_summary(client):
    """analyze() must parse choices[0].message.content and strip markdown."""
    resp = client.post(
        "/api/ai/analyze",
        json={"code": "600519", "name": "贵州茅台", "context": ""},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["data"]["code"] == "600519"
    summary = body["data"]["summary"]
    assert summary  # non-empty
    # markdown cleanup removes '#' and '**' (single '*' is intentionally left,
    # see known issue noted in the project report P2).
    assert "#" not in summary
    assert "**" not in summary
    assert "贵州茅台" in summary


def test_ai_analyze_handles_upstream_error(client, monkeypatch):
    """A non-2xx from DeepSeek must surface as AI_SERVICE_ERROR, not 500."""
    fake_resp = MagicMock()
    fake_resp.raise_for_status = MagicMock(
        side_effect=Exception("402 Payment Required")
    )
    fake_http_client = MagicMock()
    fake_http_client.post = AsyncMock(return_value=fake_resp)

    import backend.app.routers.ai as ai_router

    monkeypatch.setattr(ai_router, "get_http_client", lambda: fake_http_client)

    resp = client.post(
        "/api/ai/analyze",
        json={"code": "600519", "name": "贵州茅台", "context": ""},
    )
    # Upstream failure surfaces as 502 (AIServiceError status), not 500/200.
    assert resp.status_code == 502, resp.text
    body = resp.json()
    assert body.get("error") == "AI_SERVICE_ERROR"
