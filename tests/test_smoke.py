"""Smoke tests for StockPilot backend core endpoints.

Verifies the essential startup contract end-to-end:
- app builds via create_app()
- DB schema is initialized (lifespan calls init_db())
- /api/health and /api/account are reachable with the DB ready

Uses an isolated temp DB so it never contends with a running backend
or the dev database.
"""
import tempfile
from pathlib import Path

import pytest
from starlette.testclient import TestClient

from backend.app.main import create_app


@pytest.fixture(scope="module")
def client():
    import backend.app.core.config as cfg
    import backend.app.db.session as sess

    tmp_db = Path(tempfile.mkdtemp()) / "test_stockpilot.db"
    old_cfg, old_sess = cfg.DB_PATH, sess.DB_PATH
    cfg.DB_PATH = tmp_db
    sess.DB_PATH = tmp_db
    try:
        app = create_app()
        with TestClient(app) as c:  # triggers lifespan -> init_db() on tmp DB
            yield c
    finally:
        cfg.DB_PATH, sess.DB_PATH = old_cfg, old_sess


def test_health_ok(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["checks"]["database"] == "ok"


def test_account_reachable(client):
    r = client.get("/api/account")
    assert r.status_code == 200
    assert "data" in r.json()


def test_openapi_served(client):
    r = client.get("/openapi.json")
    assert r.status_code == 200
    assert "paths" in r.json()
