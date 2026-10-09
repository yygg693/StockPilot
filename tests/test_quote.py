"""Quote route tests for StockPilot backend.

Covers the market-data surface against an ISOLATED temp sqlite DB (so the
lifespan's init_db never touches the running backend's file). No live network:

- ``/api/quote``, ``/api/index``, ``/api/kline`` call service functions
  (get_quote / parse_index_overview / get_kline) which are replaced with
  in-process fakes.
- ``/api/search``, ``/api/breadth``, ``/api/kline/minute`` call the shared
  httpx client directly, so we inject a fake client returning canned
  responses and assert the route's PARSING logic (GBK smartbox, gtimg
  breadth lines, minute JSON).

Run with:
    python -m pytest tests/test_quote.py -v -p no:cacheprovider
"""
from __future__ import annotations

import json
import os
from unittest.mock import MagicMock

import pytest
from starlette.testclient import TestClient

os.environ.setdefault("STOCKPILOT_SECURITY_AUTH_ENABLED", "false")


class _FakeResponse:
    """Minimal stand-in for an httpx response used by quote routes."""

    def __init__(self, text: str = "", content: bytes = b"", json_data=None):
        self.text = text
        self.content = content
        self._json = json_data

    def json(self):
        if self._json is not None:
            return self._json
        raise ValueError("no json payload")

    def raise_for_status(self):
        return None


class _FakeHttpClient:
    """Routes a URL substring to a canned _FakeResponse."""

    def __init__(self, responses: dict[str, _FakeResponse]):
        self._responses = responses

    async def get(self, url: str, **kwargs):
        for key, resp in self._responses.items():
            if key in url:
                return resp
        return _FakeResponse(text="")


@pytest.fixture
def quote_client(tmp_path, monkeypatch):
    import backend.app.core.config as cfg
    import backend.app.db.session as sess
    import backend.app.deps as deps
    import backend.app.routers.quote as quote

    db_file = tmp_path / "quote_test.db"
    monkeypatch.setattr(cfg, "DB_PATH", db_file)
    monkeypatch.setattr(sess, "DB_PATH", db_file)
    monkeypatch.setattr(deps, "_cache", None)

    # Service-function fakes (the route passes the http client but we ignore it).
    async def _fake_quote(client, code: str) -> dict:
        return {"code": code, "name": "测试标的", "price": 100.0,
                "prev_close": 98.0, "change_pct": 2.04}

    async def _fake_kline(client, code: str, period: str = "day", count: int = 120) -> list:
        return [{"date": "2026-08-22", "open": 99, "close": 100,
                 "high": 101, "low": 98, "volume": 1000}]

    async def _fake_index(client, codes: list) -> list:
        return [{"code": "sh000001", "name": "上证指数",
                 "price": 3200.0, "change_pct": 0.5}]

    monkeypatch.setattr(quote, "get_quote", _fake_quote)
    monkeypatch.setattr(quote, "get_kline", _fake_kline)
    monkeypatch.setattr(quote, "parse_index_overview", _fake_index)

    from backend.app.main import create_app

    app = create_app()
    with TestClient(app) as c:
        yield c


# --- quote / index / kline (service fakes) ---------------------------------

def test_quote_returns_data(quote_client):
    r = quote_client.get("/api/quote", params={"code": "sh600519"})
    assert r.status_code == 200, r.text
    d = r.json()["data"]
    assert d["code"] == "sh600519"
    assert d["price"] == 100.0


def test_quote_not_found_404(quote_client, monkeypatch):
    import backend.app.routers.quote as quote

    async def _none(client, code):
        return None

    monkeypatch.setattr(quote, "get_quote", _none)
    r = quote_client.get("/api/quote", params={"code": "sh000000"})
    assert r.status_code == 404, r.text
    assert r.json()["error"] == "NOT_FOUND"


def test_index_overview(quote_client):
    r = quote_client.get("/api/index")
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert isinstance(data, list) and data[0]["name"] == "上证指数"


def test_kline(quote_client):
    r = quote_client.get("/api/kline", params={"code": "sh600519", "period": "day", "count": 120})
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert isinstance(data, list) and data[0]["close"] == 100


# --- search (GBK smartbox parsing) -----------------------------------------

def test_search_parses_smartbox(quote_client, monkeypatch):
    import backend.app.routers.quote as quote

    payload = 'v_hint="sh600519~600519~贵州茅台^sz000858~000858~五粮液"'
    fake = _FakeHttpClient({"smartbox": _FakeResponse(content=payload.encode("gbk"))})
    monkeypatch.setattr(quote, "get_http_client", lambda: fake)

    r = quote_client.get("/api/search", params={"q": "茅台"})
    assert r.status_code == 200, r.text
    results = r.json()["data"]
    assert {it["code"] for it in results} == {"sh600519", "sz000858"}
    names = {it["code"]: it["name"] for it in results}
    assert names["sh600519"] == "贵州茅台"
    assert names["sz000858"] == "五粮液"


def test_search_empty_result(quote_client, monkeypatch):
    import backend.app.routers.quote as quote

    # No v_hint match -> empty list, route must not 500.
    fake = _FakeHttpClient({"smartbox": _FakeResponse(content=b'v_hint=""')})
    monkeypatch.setattr(quote, "get_http_client", lambda: fake)

    r = quote_client.get("/api/search", params={"q": "zzz"})
    assert r.status_code == 200, r.text
    assert r.json()["data"] == []


# --- breadth (gtimg line parsing + computation) ----------------------------

def _breadth_line(code: str, pct: float, amount: float) -> str:
    """Build a synthetic gtimg quote line with >=38 fields; field 32 = pct,
    field 37 = amount (matching quote.py's breadth parser)."""
    fields = [f"f{i}" for i in range(38)]
    fields[32] = f"{pct}"
    fields[37] = f"{amount}"
    return f'v_{code}="{"~".join(fields)}"'


def test_breadth_parses_and_computes(quote_client, monkeypatch):
    import backend.app.routers.quote as quote

    text = ";".join([
        _breadth_line("sh600519", 2.5, 1_000_000),
        _breadth_line("sz000858", -3.0, 2_000_000),
    ])
    fake = _FakeHttpClient({"qt.gtimg.cn/q=": _FakeResponse(text=text)})
    monkeypatch.setattr(quote, "get_http_client", lambda: fake)

    r = quote_client.get("/api/breadth")
    assert r.status_code == 200, r.text
    d = r.json()["data"]
    assert d["up"] == 1
    assert d["down"] == 1
    assert d["flat"] == 0
    assert d["total_amount"] == 3_000_000.0
    assert d["avg_pct"] == -0.25  # (2.5 - 3.0) / 2
    assert d["up_pct"] == 50.0


# --- kline minute (JSON parsing) -------------------------------------------

def test_kline_minute_parses(quote_client, monkeypatch):
    import backend.app.routers.quote as quote

    json_data = {"code": 0, "data": {"sh600519": {"m5": [
        ["2026-08-22 09:30", "99", "100", "101", "98", "1000"]
    ]}}}
    fake = _FakeHttpClient({"mkline": _FakeResponse(json_data=json_data)})
    monkeypatch.setattr(quote, "get_http_client", lambda: fake)

    r = quote_client.get("/api/kline/minute", params={"code": "sh600519", "period": "m5", "count": 120})
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert isinstance(data, list) and data[0]["close"] == 100.0
    assert data[0]["volume"] == 1000.0
