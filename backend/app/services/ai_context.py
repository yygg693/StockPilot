"""AI context builder - gathers all user data for intelligent responses.

P0-3 fix: All data now read from SQLite (unified storage layer).
Previously used in-memory dicts that were disconnected from the trade router's
SQLite data, causing AI to see stale/empty positions and lose trades on restart.
"""
from __future__ import annotations

from backend.app.core.http_client import get_http_client
from backend.app.core.logging import get_logger
from backend.app.db.session import get_db
from backend.app.services.data_tencent import fetch_quote_batch

logger = get_logger("ai.context")

INITIAL_CASH = 1_000_000.0


async def get_trade_db() -> dict:
    """Read current portfolio state from SQLite (replaces in-memory dict).

    Returns a dict with keys: cash, positions, history — same shape as before
    for backward compatibility, but now backed by persistent storage.
    """
    db = await get_db()

    # Ensure account exists
    await db.execute(
        "INSERT OR IGNORE INTO account (id, cash, initial_cash) VALUES (1, ?, ?)",
        (INITIAL_CASH, INITIAL_CASH),
    )

    # Cash
    cursor = await db.execute("SELECT cash FROM account WHERE id=1")
    row = await cursor.fetchone()
    cash = float(row["cash"]) if row else INITIAL_CASH

    # Positions
    cursor = await db.execute("SELECT * FROM positions ORDER BY created_at DESC")
    positions = []
    for r in await cursor.fetchall():
        d = dict(r)
        positions.append({
            "code": d["code"],
            "name": d.get("name", ""),
            "qty": d["qty"],
            "cost_price": d["cost"],
            "asset_type": d.get("type", "stock"),
        })

    # Recent trade history
    cursor = await db.execute(
        "SELECT * FROM trade_log ORDER BY created_at DESC LIMIT 20"
    )
    history = []
    for r in await cursor.fetchall():
        d = dict(r)
        history.append({
            "side": d.get("action", ""),
            "code": d["code"],
            "name": d.get("name", ""),
            "qty": d["qty"],
            "price": d["price"],
        })

    return {"cash": cash, "positions": positions, "history": history}


async def get_watchlist_store() -> list[dict]:
    """Read watchlist from SQLite (replaces in-memory list)."""
    db = await get_db()
    cursor = await db.execute("SELECT * FROM watchlist ORDER BY added_at DESC")
    items = []
    for r in await cursor.fetchall():
        d = dict(r)
        items.append({
            "code": d["code"],
            "name": d.get("name", ""),
            "type": d.get("type", "stock"),
        })
    return items


async def build_ai_context(page: str = "", asset_code: str = "", asset_name: str = "") -> str:
    """Build comprehensive context string for AI."""
    parts = []

    # 1. Market overview
    try:
        client = get_http_client()
        idx_codes = ["sh000001", "sz399001", "sz399006"]
        quotes = await fetch_quote_batch(client, idx_codes)
        idx_lines = []
        for c in idx_codes:
            q = quotes.get(c)
            if q:
                pct = q.get("change_pct", 0)
                idx_lines.append(f"{q.get('name', c)} {q.get('price', '--')} ({'+' if pct >= 0 else ''}{pct:.2f}%)")
        if idx_lines:
            parts.append("【大盘】" + "; ".join(idx_lines))
    except Exception:
        pass

    # 2. User portfolio (from SQLite)
    db = await get_trade_db()
    if db["positions"]:
        pos_lines = []
        for p in db["positions"][:10]:
            pos_lines.append(f"{p.get('name', p.get('code'))} {p.get('qty')}股 成本{p.get('cost_price', '--')}")
        parts.append(f"【持仓】可用资金{db['cash']:.0f}元, 持仓: " + "; ".join(pos_lines))
    else:
        parts.append(f"【持仓】可用资金{db['cash']:.0f}元, 暂无持仓")

    # 3. Watchlist (from SQLite)
    wl = await get_watchlist_store()
    if wl:
        wl_names = [w.get("name", w.get("code", "")) for w in wl[:8]]
        parts.append("【自选】" + ", ".join(wl_names))

    # 4. Current asset context
    if asset_code:
        parts.append(f"【当前查看】{asset_name}({asset_code})")

    # 5. Recent trades
    if db["history"]:
        recent = db["history"][:3]
        trade_lines = [f"{t.get('side','')} {t.get('name','')} {t.get('qty','')}股@{t.get('price','')}" for t in recent]
        parts.append("【最近交易】" + "; ".join(trade_lines))

    return "\n".join(parts)
