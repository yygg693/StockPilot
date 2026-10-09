"""Async SQLite session management (aiosqlite)."""
from __future__ import annotations

import aiosqlite

from backend.app.core.config import DB_PATH

_conn: aiosqlite.Connection | None = None

SCHEMA = """
CREATE TABLE IF NOT EXISTS positions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code TEXT NOT NULL,
    name TEXT DEFAULT '',
    type TEXT DEFAULT 'stock',
    qty REAL NOT NULL DEFAULT 0,
    cost REAL NOT NULL DEFAULT 0,
    created_at TEXT DEFAULT (datetime('now','localtime'))
);
CREATE TABLE IF NOT EXISTS trade_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code TEXT NOT NULL,
    name TEXT DEFAULT '',
    type TEXT DEFAULT 'stock',
    action TEXT NOT NULL,
    qty REAL NOT NULL,
    price REAL NOT NULL,
    amount REAL NOT NULL,
    note TEXT DEFAULT '',
    created_at TEXT DEFAULT (datetime('now','localtime'))
);
CREATE TABLE IF NOT EXISTS watchlist (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code TEXT NOT NULL UNIQUE,
    name TEXT DEFAULT '',
    type TEXT DEFAULT 'stock',
    added_at TEXT DEFAULT (datetime('now','localtime'))
);
CREATE TABLE IF NOT EXISTS account (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    cash REAL NOT NULL DEFAULT 1000000,
    initial_cash REAL NOT NULL DEFAULT 1000000,
    updated_at TEXT DEFAULT (datetime('now','localtime'))
);
INSERT OR IGNORE INTO account (id, cash, initial_cash) VALUES (1, 1000000, 1000000);
CREATE TABLE IF NOT EXISTS audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT DEFAULT (datetime('now','localtime')),
    user_id TEXT DEFAULT 'anonymous',
    action TEXT NOT NULL,
    target TEXT DEFAULT '',
    detail TEXT DEFAULT '{}',
    ip_address TEXT DEFAULT '',
    user_agent TEXT DEFAULT ''
);
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    password_salt TEXT NOT NULL,
    display_name TEXT DEFAULT '',
    role TEXT DEFAULT 'user',
    is_active INTEGER DEFAULT 1,
    created_at TEXT DEFAULT (datetime('now','localtime')),
    last_login TEXT DEFAULT ''
);
CREATE TABLE IF NOT EXISTS kline_cache (
    code TEXT NOT NULL,
    period TEXT NOT NULL,
    data_json TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    bar_count INTEGER DEFAULT 0,
    PRIMARY KEY (code, period)
);
CREATE TABLE IF NOT EXISTS quote_cache (
    code TEXT PRIMARY KEY,
    data_json TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS suitability_profile (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    risk_level TEXT NOT NULL DEFAULT 'C2',
    score INTEGER NOT NULL DEFAULT 0,
    questionnaire_json TEXT NOT NULL DEFAULT '{}',
    assessed_at TEXT DEFAULT (datetime('now','localtime')),
    expires_at TEXT DEFAULT ''
);
INSERT OR IGNORE INTO suitability_profile (id, risk_level, score) VALUES (1, 'C2', 0);
CREATE TABLE IF NOT EXISTS ai_analysis_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code TEXT NOT NULL,
    signal TEXT NOT NULL,
    score INTEGER DEFAULT 0,
    confidence INTEGER DEFAULT 0,
    indicators_json TEXT DEFAULT '{}',
    ai_commentary TEXT DEFAULT '',
    model TEXT DEFAULT '',
    created_at TEXT DEFAULT (datetime('now','localtime'))
);
"""


async def init_db() -> None:
    global _conn
    _conn = await aiosqlite.connect(str(DB_PATH), timeout=30)
    _conn.row_factory = aiosqlite.Row
    # Robust SQLite settings: WAL mode + high busy_timeout
    await _conn.execute("PRAGMA journal_mode=WAL")
    await _conn.execute("PRAGMA busy_timeout=15000")
    await _conn.execute("PRAGMA wal_autocheckpoint=1000")
    await _conn.execute("PRAGMA foreign_keys=ON")
    for stmt in SCHEMA.split(";"):
        stmt = stmt.strip()
        if stmt:
            await _conn.execute(stmt)
    await _conn.commit()


async def get_db() -> aiosqlite.Connection:
    global _conn
    if _conn is None:
        await init_db()
    return _conn


async def close_db() -> None:
    global _conn
    if _conn:
        await _conn.close()
        _conn = None
