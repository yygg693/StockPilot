"""Async tests: verify pytest-asyncio wiring + core async init paths.

Purpose:
- Prove that ``asyncio_mode = auto`` actually *executes* async test functions.
  Without the pytest-asyncio plugin installed, pytest would flag the
  ``asyncio_mode`` option as unknown (warning) and would not run async tests.
- Cover the async DB lifecycle (init_db / get_db / close_db) against an
  isolated temp sqlite file, and the shared http_client lifecycle. No real
  network or the running backend's database is touched.
"""
from __future__ import annotations

import httpx
import pytest

import backend.app.db.session as db_session
from backend.app.core import http_client


@pytest.fixture
def isolate_db(tmp_path, monkeypatch):
    """Redirect the session module's DB_PATH to a fresh temp sqlite file so we
    never touch (and lock) the running backend's real database."""
    db_file = tmp_path / "test_async.db"
    monkeypatch.setattr(db_session, "DB_PATH", db_file)
    yield db_file
    # best-effort cleanup of WAL sidecar files
    for suffix in ("", "-wal", "-shm", "-journal"):
        candidate = db_file.parent / (db_file.name + suffix)
        if candidate.exists():
            try:
                candidate.unlink()
            except OSError:
                pass


async def test_init_db_creates_schema_and_seeds_account(isolate_db):
    await db_session.init_db()
    try:
        db = await db_session.get_db()
        async with db.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ) as cur:
            rows = await cur.fetchall()
        names = {r[0] for r in rows}
        # Core tables declared in session.SCHEMA
        assert {
            "positions",
            "trade_log",
            "watchlist",
            "account",
            "users",
            "kline_cache",
            "quote_cache",
            "ai_analysis_log",
            "suitability_profile",
            "audit_log",
        } <= names
        # account seeded with default cash
        async with db.execute("SELECT cash FROM account WHERE id=1") as cur:
            row = await cur.fetchone()
        assert row is not None and row[0] == 1_000_000
    finally:
        await db_session.close_db()


async def test_http_client_lifecycle():
    await http_client.init_http_client()
    try:
        client = http_client.get_http_client()
        assert client is not None
        assert isinstance(client, httpx.AsyncClient)
        assert client.is_closed is False
    finally:
        await http_client.close_http_client()
