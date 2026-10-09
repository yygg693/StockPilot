"""SQLite 存储：自选列表管理。"""
import sqlite3
import threading
from datetime import datetime

from backend.config import DB_PATH

_LOCK = threading.Lock()


def _conn():
    c = sqlite3.connect(DB_PATH)
    c.row_factory = sqlite3.Row
    return c


def init_db():
    with _LOCK, _conn() as c:
        c.execute("""
            CREATE TABLE IF NOT EXISTS watchlist (
                code TEXT NOT NULL,
                name TEXT,
                type TEXT NOT NULL,
                grp  TEXT DEFAULT '默认',
                added_at TEXT,
                PRIMARY KEY (code, type)
            )
        """)
        # 模拟盘持仓表
        c.execute("""
            CREATE TABLE IF NOT EXISTS positions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                code TEXT NOT NULL,
                name TEXT,
                type TEXT NOT NULL,
                qty REAL NOT NULL,
                cost REAL NOT NULL,
                opened_at TEXT
            )
        """)
        c.commit()


def add_watch(code, name, asset_type, grp="默认"):
    with _LOCK, _conn() as c:
        c.execute(
            "INSERT OR REPLACE INTO watchlist (code, name, type, grp, added_at) "
            "VALUES (?,?,?,?,?)",
            (code, name, asset_type, grp, datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
        )
        c.commit()
    return True


def remove_watch(code, asset_type):
    with _LOCK, _conn() as c:
        c.execute("DELETE FROM watchlist WHERE code=? AND type=?", (code, asset_type))
        c.commit()
    return True


def list_watch():
    with _LOCK, _conn() as c:
        rows = c.execute(
            "SELECT code, name, type, grp, added_at FROM watchlist ORDER BY added_at DESC"
        ).fetchall()
    return [dict(r) for r in rows]


# --------------------------------------------------------------- 模拟盘持仓
def buy_position(code, name, asset_type, qty, cost):
    with _LOCK, _conn() as c:
        row = c.execute(
            "SELECT id, qty, cost FROM positions WHERE code=? AND type=?",
            (code, asset_type),
        ).fetchone()
        if row:
            old_qty, old_cost = row["qty"], row["cost"]
            new_qty = old_qty + qty
            new_cost = (old_qty * old_cost + qty * cost) / new_qty if new_qty else cost
            c.execute(
                "UPDATE positions SET qty=?, cost=? WHERE id=?",
                (new_qty, new_cost, row["id"]),
            )
        else:
            c.execute(
                "INSERT INTO positions (code, name, type, qty, cost, opened_at) "
                "VALUES (?,?,?,?,?,?)",
                (code, name, asset_type, qty, cost,
                 datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
            )
        c.commit()


def sell_position(code, asset_type, qty):
    """卖出持仓。返回 True=成功, False=无持仓, None=数量不足。"""
    with _LOCK, _conn() as c:
        row = c.execute(
            "SELECT id, qty, cost FROM positions WHERE code=? AND type=?",
            (code, asset_type),
        ).fetchone()
        if not row:
            return False
        if qty > row["qty"] + 1e-9:
            return None  # 卖出数量超过持仓
        remain = row["qty"] - qty
        if remain <= 1e-9:
            c.execute("DELETE FROM positions WHERE id=?", (row["id"],))
        else:
            c.execute("UPDATE positions SET qty=? WHERE id=?",
                      (remain, row["id"]))
        c.commit()
        return True


def list_positions():
    with _LOCK, _conn() as c:
        rows = c.execute(
            "SELECT id, code, name, type, qty, cost, opened_at FROM positions"
        ).fetchall()
    return [dict(r) for r in rows]
