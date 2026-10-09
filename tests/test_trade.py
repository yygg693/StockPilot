"""Trade route tests for StockPilot backend.

Covers the simulated-trading surface end-to-end against an ISOLATED temp
sqlite database (never the running backend's stockpilot_v2.db, which may be
locked). No live market data is touched: the quote-enrichment helpers
``_fetch_quotes`` / ``_fetch_fund_nav`` are replaced with deterministic
in-process fakes so the PnL / market-value math in ``_enrich_positions`` is
fully testable.

Routes exercised:
- GET  /api/account            (cash + live-valued positions)
- GET  /api/positions
- POST /api/trade/buy          (new + average-cost top-up, cash check)
- POST /api/trade/sell         (full/partial, position/cash guards)
- GET  /api/trade/history
- POST /api/trade/reset-account
- GET/POST /api/watchlist, /api/watchlist/add, /api/watchlist/remove

Run with:
    python -m pytest tests/test_trade.py -v -p no:cacheprovider
"""
from __future__ import annotations

import pytest
from starlette.testclient import TestClient

# Make sure the dev auth bypass is on before any Settings() is constructed.
import os

os.environ.setdefault("STOCKPILOT_SECURITY_AUTH_ENABLED", "false")


@pytest.fixture
def trade_client(tmp_path, monkeypatch):
    import backend.app.core.config as cfg
    import backend.app.db.session as sess
    import backend.app.deps as deps
    import backend.app.routers.trade as trade

    # Redirect the DB to a fresh temp file (session.py keeps its own copy of
    # DB_PATH, so monkeypatch both names).
    db_file = tmp_path / "trade_test.db"
    monkeypatch.setattr(cfg, "DB_PATH", db_file)
    monkeypatch.setattr(sess, "DB_PATH", db_file)

    # Fresh in-memory cache per test (avoid cross-test contamination).
    monkeypatch.setattr(deps, "_cache", None)

    # Deterministic quotes so enrichment math is reproducible.
    fake_quotes = {
        "sh600519": {"price": 1800.0, "prev_close": 1750.0, "change_pct": 2.86},
        "sz000858": {"price": 150.0, "prev_close": 155.0, "change_pct": -3.23},
    }
    fake_navs = {
        "012345": {"price": 1.25, "change_pct": 1.0, "nav": 1.25, "nav_date": "20260822"},
    }

    async def _fake_fetch_quotes(codes):
        return {c: fake_quotes.get(c, {}) for c in codes}

    async def _fake_fetch_fund_nav(codes):
        out = {}
        for c in codes:
            raw = c.replace("sh", "").replace("sz", "")
            if raw in fake_navs:
                out[raw] = fake_navs[raw]
        return out

    monkeypatch.setattr(trade, "_fetch_quotes", _fake_fetch_quotes)
    monkeypatch.setattr(trade, "_fetch_fund_nav", _fake_fetch_fund_nav)

    from backend.app.main import create_app

    app = create_app()
    with TestClient(app) as c:  # lifespan -> init_db() on the temp DB
        yield c


# --- Account baseline -------------------------------------------------------

def test_account_initial_state(trade_client):
    r = trade_client.get("/api/account")
    assert r.status_code == 200, r.text
    d = r.json()["data"]
    assert d["cash"] == 1_000_000.0
    assert d["initial_cash"] == 1_000_000.0
    assert d["market_value"] == 0.0
    assert d["position_count"] == 0
    assert d["positions"] == []


# --- Buy --------------------------------------------------------------------

def test_buy_creates_position_and_reduces_cash(trade_client):
    r = trade_client.post(
        "/api/trade/buy",
        json={"code": "sh600519", "name": "贵州茅台", "asset_type": "stock",
              "qty": 100, "price": 1700},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ok"] is True
    assert body["cash"] == 830_000.0  # 1,000,000 - 170,000

    acct = trade_client.get("/api/account").json()["data"]
    assert acct["position_count"] == 1
    # mock price 1800 -> market value 180,000; pnl = 180,000 - 170,000 = 10,000
    assert acct["market_value"] == 180_000.0
    assert acct["total_assets"] == 1_010_000.0
    assert acct["total_pnl"] == 10_000.0
    assert acct["positions"][0]["pnl"] == 10_000.0


def test_buy_averaging_topup(trade_client):
    trade_client.post("/api/trade/buy", json={"code": "sh600519", "asset_type": "stock", "qty": 100, "price": 1700})
    # Buy 100 more at a higher price -> average cost should be (1700+1900)/2 = 1800
    r = trade_client.post("/api/trade/buy", json={"code": "sh600519", "asset_type": "stock", "qty": 100, "price": 1900})
    assert r.status_code == 200, r.text
    acct = trade_client.get("/api/account").json()["data"]
    assert acct["position_count"] == 1
    pos = acct["positions"][0]
    assert pos["qty"] == 200
    assert pos["cost"] == 1800.0
    # cash: 1,000,000 - 170,000 - 190,000 = 640,000
    assert acct["cash"] == 640_000.0


def test_buy_insufficient_cash_rejected(trade_client):
    r = trade_client.post(
        "/api/trade/buy",
        json={"code": "sh600519", "asset_type": "stock", "qty": 10000, "price": 1800},
    )
    assert r.status_code == 400, r.text
    assert r.json()["error"] == "INSUFFICIENT_CASH"


# --- Sell -------------------------------------------------------------------

def test_sell_full_position_records_pnl(trade_client):
    trade_client.post("/api/trade/buy", json={"code": "sh600519", "asset_type": "stock", "qty": 100, "price": 1700})
    r = trade_client.post(
        "/api/trade/sell",
        json={"code": "sh600519", "asset_type": "stock", "qty": 100, "price": 1800},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ok"] is True
    assert body["pnl"] == 10_000.0  # (1800 - 1700) * 100
    # cash: 830,000 + 180,000 = 1,010,000
    assert body["cash"] == 1_010_000.0

    acct = trade_client.get("/api/account").json()["data"]
    assert acct["position_count"] == 0
    assert acct["cash"] == 1_010_000.0


def test_sell_partial_position(trade_client):
    trade_client.post("/api/trade/buy", json={"code": "sh600519", "asset_type": "stock", "qty": 100, "price": 1700})
    r = trade_client.post("/api/trade/sell", json={"code": "sh600519", "asset_type": "stock", "qty": 40, "price": 1800})
    assert r.status_code == 200, r.text
    acct = trade_client.get("/api/account").json()["data"]
    assert acct["position_count"] == 1
    assert acct["positions"][0]["qty"] == 60
    # cash: 830,000 + 72,000 = 902,000
    assert acct["cash"] == 902_000.0


def test_sell_unknown_position_404(trade_client):
    r = trade_client.post("/api/trade/sell", json={"code": "sh600519", "asset_type": "stock", "qty": 10, "price": 100})
    assert r.status_code == 404, r.text
    assert r.json()["error"] == "POSITION_NOT_FOUND"


def test_sell_exceeds_holding_400(trade_client):
    trade_client.post("/api/trade/buy", json={"code": "sh600519", "asset_type": "stock", "qty": 100, "price": 1700})
    r = trade_client.post("/api/trade/sell", json={"code": "sh600519", "asset_type": "stock", "qty": 200, "price": 100})
    assert r.status_code == 400, r.text
    assert r.json()["error"] == "INSUFFICIENT_POSITION"


# --- Trade history ----------------------------------------------------------

def test_trade_history_records_buy_and_sell(trade_client):
    trade_client.post("/api/trade/buy", json={"code": "sh600519", "asset_type": "stock", "qty": 100, "price": 1700})
    trade_client.post("/api/trade/sell", json={"code": "sh600519", "asset_type": "stock", "qty": 50, "price": 1800})
    r = trade_client.get("/api/trade/history")
    assert r.status_code == 200, r.text
    rows = r.json()["data"]
    assert len(rows) >= 2
    actions = {row["action"] for row in rows}
    assert "buy" in actions and "sell" in actions


# --- Reset ------------------------------------------------------------------

def test_reset_account_clears_everything(trade_client):
    trade_client.post("/api/trade/buy", json={"code": "sh600519", "asset_type": "stock", "qty": 100, "price": 1700})
    assert trade_client.get("/api/account").json()["data"]["position_count"] == 1

    r = trade_client.post("/api/trade/reset-account")
    assert r.status_code == 200, r.text
    assert r.json()["data"]["cash"] == 1_000_000.0

    acct = trade_client.get("/api/account").json()["data"]
    assert acct["position_count"] == 0
    assert acct["cash"] == 1_000_000.0
    assert trade_client.get("/api/trade/history").json()["data"] == []


# --- Fund positions (NAV enrichment branch) ---------------------------------

def test_buy_fund_position_enriches_nav(trade_client):
    r = trade_client.post(
        "/api/trade/buy",
        json={"code": "sz012345", "name": "测试基金", "asset_type": "fund",
              "qty": 1000, "price": 1.20},
    )
    assert r.status_code == 200, r.text
    acct = trade_client.get("/api/account").json()["data"]
    assert acct["position_count"] == 1
    pos = acct["positions"][0]
    assert pos["type"] == "fund"
    # mock NAV 1.25 -> market value 1,250; pnl = 1,250 - 1,200 = 50
    assert pos["price"] == 1.25
    assert pos["market_value"] == 1250.0
    assert pos["pnl"] == 50.0


# --- Watchlist --------------------------------------------------------------

def test_watchlist_add_then_list(trade_client):
    add = trade_client.post("/api/watchlist/add", params={"code": "sh600519", "name": "贵州茅台"})
    assert add.status_code == 200, add.text
    assert add.json()["ok"] is True

    lst = trade_client.get("/api/watchlist")
    assert lst.status_code == 200, lst.text
    codes = {it["code"] for it in lst.json()["data"]}
    assert "sh600519" in codes


def test_watchlist_add_duplicate_reports_conflict(trade_client):
    trade_client.post("/api/watchlist/add", params={"code": "sh600519"})
    second = trade_client.post("/api/watchlist/add", params={"code": "sh600519"})
    assert second.status_code == 200, second.text
    body = second.json()
    assert body["ok"] is False
    assert body["message"] == "Already in watchlist"


def test_watchlist_remove(trade_client):
    trade_client.post("/api/watchlist/add", params={"code": "sh600519"})
    rem = trade_client.post("/api/watchlist/remove", params={"code": "sh600519"})
    assert rem.status_code == 200, rem.text
    assert rem.json()["ok"] is True
    assert trade_client.get("/api/watchlist").json()["data"] == []
