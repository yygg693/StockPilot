"""Trade routes: simulated portfolio management (account/buy/sell/positions/AI auto-trade)."""
from __future__ import annotations

import asyncio
from functools import wraps

import aiosqlite
from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field

from backend.app.core.audit import extract_request_info, log_audit
from backend.app.core.exceptions import (
    InsufficientCashError,
    InsufficientPositionError,
    PositionNotFoundError,
)
from backend.app.core.http_client import get_http_client
from backend.app.core.logging import get_logger
from backend.app.db.session import get_db
from backend.app.deps import get_current_user
from backend.app.services.data_source import get_quote_batch

logger = get_logger("trade")
router = APIRouter(dependencies=[Depends(get_current_user)])

# SQLite uses one shared connection. Serialize account mutations so concurrent
# requests cannot spend the same observed balance twice.
_trade_lock = asyncio.Lock()


def _serialized_trade(handler):
    @wraps(handler)
    async def wrapper(*args, **kwargs):
        async with _trade_lock:
            return await handler(*args, **kwargs)

    return wrapper

INITIAL_CASH = 1_000_000.0


class TradeRequest(BaseModel):
    code: str
    name: str = ""
    asset_type: str = "stock"
    qty: float = Field(gt=0)
    price: float = Field(gt=0)
    note: str = ""


class AutoBuyRequest(BaseModel):
    strategy: str = "oversold_bounce"
    universe: str = "hs300"
    top_n: int = Field(default=5, ge=1, le=20)
    max_position_pct: float = Field(default=0.2, gt=0, le=1.0)


class AutoSellRequest(BaseModel):
    stop_loss_pct: float = Field(default=8.0, ge=0, le=50)
    take_profit_pct: float = Field(default=20.0, ge=0, le=200)


# --- Account / cash helpers ---

async def _ensure_account(db) -> None:
    """Ensure the single-row account record exists (for legacy DBs)."""
    await db.execute(
        "INSERT OR IGNORE INTO account (id, cash, initial_cash) VALUES (1, ?, ?)",
        (INITIAL_CASH, INITIAL_CASH),
    )


async def _get_cash(db) -> float:
    await _ensure_account(db)
    cursor = await db.execute("SELECT cash FROM account WHERE id=1")
    row = await cursor.fetchone()
    return float(row["cash"]) if row else INITIAL_CASH


async def _set_cash(db, cash: float) -> None:
    await _ensure_account(db)
    await db.execute(
        "UPDATE account SET cash=?, updated_at=datetime('now','localtime') WHERE id=1",
        (round(cash, 2),),
    )


# Short-lived per-code quote cache (10s) — account/positions/watchlist overlap heavily
_QUOTE_TTL = 10.0
_quote_cache: dict[str, tuple[float, dict]] = {}
_fund_nav_cache: dict[str, tuple[float, dict]] = {}


async def _fetch_quotes(codes: list[str]) -> dict[str, dict]:
    """Batch-fetch real-time quotes with a 10s per-code cache."""
    if not codes:
        return {}
    import time as _time
    now = _time.time()
    result: dict[str, dict] = {}
    missing: list[str] = []
    for c in codes:
        ent = _quote_cache.get(c)
        if ent and now - ent[0] < _QUOTE_TTL:
            result[c] = ent[1]
        else:
            missing.append(c)
    if missing:
        try:
            client = get_http_client()
            fresh = await get_quote_batch(client, missing)
            for c, q in fresh.items():
                _quote_cache[c] = (now, q)
                result[c] = q
        except Exception as e:  # noqa: BLE001 - quote failure should not break account view
            logger.warning("trade.quote_failed", error=str(e))
    return result


async def _fetch_fund_nav(codes: list[str]) -> dict[str, dict]:
    """Batch-fetch fund NAV via Tencent jj-prefix API with a 10s per-code cache.

    Returns {raw_code: {price, change_pct, ...}}.
    """
    if not codes:
        return {}
    import time as _time
    now = _time.time()
    result: dict[str, dict] = {}
    missing: list[str] = []
    for c in codes:
        raw = c.replace("sh", "").replace("sz", "")
        ent = _fund_nav_cache.get(raw)
        if ent and now - ent[0] < _QUOTE_TTL:
            result[raw] = ent[1]
        else:
            missing.append(c)
    if not missing:
        return result
    try:
        import re as _re
        client = get_http_client()
        # codes like ["sz023977", ...] -> jj023977
        fund_codes = ["jj" + c.replace("sh", "").replace("sz", "") for c in missing]
        code_str = ",".join(fund_codes)
        r = await client.get(
            f"https://qt.gtimg.cn/q={code_str}",
            headers={"Referer": "https://finance.qq.com"},
            timeout=8.0,
        )
        for line in r.text.strip().split(";"):
            line = line.strip()
            if not line or "=" not in line:
                continue
            m = _re.match(r'v_jj(\w+)="(.*)"', line)
            if not m:
                continue
            fields = m.group(2).split("~")
            if len(fields) < 8:
                continue
            try:
                raw_code = fields[0] or m.group(1)
                nav = float(fields[5]) if fields[5] else 0
                chg_pct = float(fields[7]) if fields[7] else 0
                entry = {
                    "price": nav,
                    "change_pct": chg_pct,
                    "nav": nav,
                    "nav_date": fields[8] if len(fields) > 8 else "",
                }
                result[raw_code] = entry
                _fund_nav_cache[raw_code] = (now, entry)
            except (ValueError, IndexError):
                continue
        return result
    except Exception as e:
        logger.warning("trade.fund_nav_failed", error=str(e))
        return result


async def _enrich_positions(db) -> tuple[list[dict], float, float, float]:
    """Return (positions, market_value, total_cost, today_pnl) with live prices."""
    cursor = await db.execute("SELECT * FROM positions ORDER BY created_at DESC")
    rows = [dict(r) for r in await cursor.fetchall()]

    # Fetch live quotes for stocks AND fund NAV for funds
    stock_codes = [r["code"] for r in rows if r.get("type") != "fund"]
    fund_codes = [r["code"] for r in rows if r.get("type") == "fund"]
    quotes = await _fetch_quotes(stock_codes) if stock_codes else {}
    fund_navs = await _fetch_fund_nav(fund_codes) if fund_codes else {}

    positions: list[dict] = []
    market_value = 0.0
    total_cost = 0.0
    today_pnl = 0.0
    for r in rows:
        is_fund = r.get("type") == "fund"

        if is_fund:
            # Funds: fetch live NAV to calculate real PnL
            raw_code = r["code"].replace("sh", "").replace("sz", "")
            nav_data = fund_navs.get(raw_code, {})
            current_nav = float(nav_data.get("price") or 0.0)
            change_pct = float(nav_data.get("change_pct") or 0.0)
            # Fallback to stored cost if NAV unavailable
            if current_nav <= 0:
                current_nav = float(r["cost"])
                change_pct = 0.0

            cost_val = float(r["cost"]) * float(r["qty"])
            mv = current_nav * float(r["qty"])
            pnl = mv - cost_val
            pnl_pct = (pnl / cost_val * 100) if cost_val else 0.0
            positions.append({
                **r,
                "price": round(current_nav, 4),
                "change_pct": round(change_pct, 2),
                "market_value": round(mv, 2),
                "pnl": round(pnl, 2),
                "pnl_pct": round(pnl_pct, 2),
                "today_pnl": round(pnl, 2),  # Fund PnL is cumulative since no daily prev NAV
            })
            market_value += mv
            total_cost += cost_val
        else:
            q = quotes.get(r["code"], {})
            price = float(q.get("price") or 0.0)
            prev_close = float(q.get("prev_close") or 0.0)
            change_pct = float(q.get("change_pct") or 0.0)
            cur = price if price > 0 else float(r["cost"])
            mv = cur * r["qty"]
            cost_val = r["cost"] * r["qty"]
            pnl = mv - cost_val
            pnl_pct = (pnl / cost_val * 100) if cost_val else 0.0
            day_pnl = (cur - prev_close) * r["qty"] if prev_close > 0 else 0.0
            market_value += mv
            total_cost += cost_val
            today_pnl += day_pnl
            positions.append({
                **r,
                "price": round(cur, 3),
                "change_pct": round(change_pct, 2),
                "market_value": round(mv, 2),
                "pnl": round(pnl, 2),
                "pnl_pct": round(pnl_pct, 2),
                "today_pnl": round(day_pnl, 2),
            })
    return positions, market_value, total_cost, today_pnl


@router.get("/account")
async def get_account():
    """Account summary: cash + positions valued at live prices."""
    db = await get_db()
    cash = await _get_cash(db)
    positions, market_value, total_cost, today_pnl = await _enrich_positions(db)

    cursor = await db.execute("SELECT initial_cash FROM account WHERE id=1")
    row = await cursor.fetchone()
    initial_cash = float(row["initial_cash"]) if row and row["initial_cash"] else INITIAL_CASH

    total_assets = cash + market_value
    total_pnl = total_assets - initial_cash
    total_pnl_pct = (total_pnl / initial_cash * 100) if initial_cash else 0.0

    return {"data": {
        "cash": round(cash, 2),
        "initial_cash": round(initial_cash, 2),
        "market_value": round(market_value, 2),
        "total_assets": round(total_assets, 2),
        "total_cost": round(total_cost, 2),
        "total_pnl": round(total_pnl, 2),
        "total_pnl_pct": round(total_pnl_pct, 2),
        "today_pnl": round(today_pnl, 2),
        "position_count": len(positions),
        "positions": positions,
    }}


@router.get("/positions")
async def list_positions():
    db = await get_db()
    positions, _, _, _ = await _enrich_positions(db)
    return {"data": positions}


@router.post("/trade/buy")
@_serialized_trade
async def buy(req: TradeRequest, request: Request):
    db = await get_db()
    amount = req.qty * req.price

    cash = await _get_cash(db)
    if amount > cash + 1e-6:
        raise InsufficientCashError(
            f"可用资金不足: 需要 {amount:,.0f}，当前可用 {cash:,.0f}",
            detail=f"code={req.code}",
        )

    # Check existing position
    cursor = await db.execute(
        "SELECT id, qty, cost FROM positions WHERE code=? AND type=?",
        (req.code, req.asset_type),
    )
    row = await cursor.fetchone()

    if row:
        # Average cost
        new_qty = row["qty"] + req.qty
        new_cost = (row["cost"] * row["qty"] + req.price * req.qty) / new_qty
        await db.execute(
            "UPDATE positions SET qty=?, cost=? WHERE id=?",
            (new_qty, new_cost, row["id"]),
        )
    else:
        await db.execute(
            "INSERT INTO positions (code, name, type, qty, cost) VALUES (?,?,?,?,?)",
            (req.code, req.name, req.asset_type, req.qty, req.price),
        )

    await _set_cash(db, cash - amount)

    # Trade log
    await db.execute(
        "INSERT INTO trade_log (code, name, type, action, qty, price, amount, note) VALUES (?,?,?,?,?,?,?,?)",
        (req.code, req.name, req.asset_type, "buy", req.qty, req.price, amount, req.note),
    )
    await db.commit()
    logger.info("trade.buy", code=req.code, qty=req.qty, price=req.price)

    # Audit log
    info = extract_request_info(request)
    await log_audit(
        action="trade.buy",
        target=req.code,
        detail={"name": req.name, "qty": req.qty, "price": req.price, "amount": amount, "type": req.asset_type},
        **info,
    )

    return {
        "ok": True,
        "cash": round(cash - amount, 2),
        "message": f"买入 {req.qty:.0f} 股 {req.code} @ {req.price}",
    }


@router.post("/trade/sell")
@_serialized_trade
async def sell(req: TradeRequest, request: Request):
    db = await get_db()

    cursor = await db.execute(
        "SELECT id, qty, cost FROM positions WHERE code=? AND type=?",
        (req.code, req.asset_type),
    )
    row = await cursor.fetchone()

    if not row:
        raise PositionNotFoundError(f"无持仓: {req.code}")
    if req.qty > row["qty"] + 1e-9:
        raise InsufficientPositionError(
            f"卖出数量 {req.qty:.0f} 超过持仓 {row['qty']:.0f}",
            detail=f"code={req.code}",
        )

    remain = row["qty"] - req.qty
    if remain <= 1e-9:
        await db.execute("DELETE FROM positions WHERE id=?", (row["id"],))
    else:
        await db.execute("UPDATE positions SET qty=? WHERE id=?", (remain, row["id"]))

    amount = req.qty * req.price
    pnl = (req.price - row["cost"]) * req.qty

    cash = await _get_cash(db)
    await _set_cash(db, cash + amount)

    await db.execute(
        "INSERT INTO trade_log (code, name, type, action, qty, price, amount, note) VALUES (?,?,?,?,?,?,?,?)",
        (req.code, req.name, req.asset_type, "sell", req.qty, req.price, amount, req.note),
    )
    await db.commit()
    logger.info("trade.sell", code=req.code, qty=req.qty, pnl=round(pnl, 2))

    # Audit log
    info = extract_request_info(request)
    await log_audit(
        action="trade.sell",
        target=req.code,
        detail={"name": req.name, "qty": req.qty, "price": req.price, "amount": amount, "pnl": round(pnl, 2), "type": req.asset_type},
        **info,
    )

    return {
        "ok": True,
        "pnl": round(pnl, 2),
        "cash": round(cash + amount, 2),
        "message": f"卖出 {req.qty:.0f} 股 {req.code} @ {req.price}",
    }


@router.get("/trade/history")
async def trade_history(limit: int = 50):
    db = await get_db()
    cursor = await db.execute(
        "SELECT * FROM trade_log ORDER BY created_at DESC LIMIT ?", (limit,)
    )
    rows = await cursor.fetchall()
    return {"data": [dict(r) for r in rows]}


@router.post("/trade/reset-account")
@_serialized_trade
async def reset_account(request: Request):
    """Reset the simulation account to initial state.

    Clears all positions and trade history, resets cash to 1,000,000.
    Useful when the account was overwritten by a portfolio import.
    """
    db = await get_db()
    await db.execute("DELETE FROM positions")
    await db.execute("DELETE FROM trade_log")
    await db.execute(
        "UPDATE account SET cash=?, initial_cash=?, updated_at=datetime('now','localtime') WHERE id=1",
        (INITIAL_CASH, INITIAL_CASH),
    )
    await db.commit()
    logger.info("trade.reset_account", cash=INITIAL_CASH)

    info = extract_request_info(request)
    await log_audit(
        action="trade.reset_account",
        target="account",
        detail={"cash": INITIAL_CASH, "initial_cash": INITIAL_CASH},
        **info,
    )

    return {"data": {
        "cash": INITIAL_CASH,
        "initial_cash": INITIAL_CASH,
        "message": "模拟盘已重置，初始资金 1,000,000",
    }}


# --- AI auto-trade ---

@router.post("/trade/ai-auto")
async def ai_auto_buy(req: AutoBuyRequest, request: Request):
    """Run a screener strategy, pick top N matches, create buy PROPOSAL (not executed).

    P0-2 fix: Returns a proposal requiring user confirmation via /trade/confirm-proposal.
    """
    from backend.app.core.trade_proposal import create_proposal, format_proposal_response
    from backend.app.routers.screener import _apply_strategy, _get_universe_codes

    db = await get_db()
    cash = await _get_cash(db)

    codes = await _get_universe_codes(req.universe, _get_cache())
    if not codes:
        return {"data": {"bought": [], "message": "股票池为空，无法建仓"}}

    client = get_http_client()
    all_quotes: dict[str, dict] = {}
    batch_size = 60
    sem = asyncio.Semaphore(20)

    async def _fetch(batch: list[str]) -> dict:
        async with sem:
            return await get_quote_batch(client, batch)

    tasks = [_fetch(codes[i:i + batch_size]) for i in range(0, len(codes), batch_size)]
    for r in await asyncio.gather(*tasks, return_exceptions=True):
        if isinstance(r, dict):
            all_quotes.update(r)

    matches = _apply_strategy(req.strategy, all_quotes)

    # Exclude stocks already held
    cursor = await db.execute("SELECT code FROM positions")
    held = {r["code"] for r in await cursor.fetchall()}
    candidates = [m for m in matches if m["code"] not in held][: req.top_n]

    if not candidates:
        return {"data": {"bought": [], "message": "没有符合条件的新标的（可能已全部持有）"}}

    # Equal-weight position sizing based on total assets
    positions_mv = 0.0
    cursor = await db.execute("SELECT qty, cost FROM positions")
    for r in await cursor.fetchall():
        positions_mv += r["qty"] * r["cost"]
    total_assets = cash + positions_mv
    per_slot = min(total_assets * req.max_position_pct, cash / max(1, len(candidates)))

    proposed_buys: list[dict] = []
    for m in candidates:
        price = float(m.get("price") or 0.0)
        if price <= 0:
            continue
        # Round down to board lots of 100 shares
        qty = int(per_slot / price / 100) * 100
        if qty < 100:
            continue
        amount = qty * price
        if amount > cash + 1e-6:
            qty = int(cash / price / 100) * 100
            if qty < 100:
                continue
            amount = qty * price

        proposed_buys.append({
            "action": "buy",
            "code": m["code"],
            "name": m.get("name", ""),
            "qty": qty,
            "price": round(price, 2),
            "amount": round(amount, 2),
            "reason": m.get("reason", ""),
        })

    logger.info("trade.ai_auto_proposal", strategy=req.strategy, proposed=len(proposed_buys))

    # Audit log
    info = extract_request_info(request)
    await log_audit(
        action="trade.ai_auto_buy.proposal",
        target=req.strategy,
        detail={"universe": req.universe, "scanned": len(all_quotes), "matched": len(matches), "proposed": proposed_buys},
        **info,
    )

    # Create proposal (NOT executing trades)
    proposal = create_proposal(
        sells=[],
        buys=proposed_buys,
        signals_summary=[{"strategy": req.strategy, "scanned": len(all_quotes), "matched": len(matches)}],
    )
    return format_proposal_response(proposal)


@router.post("/trade/ai-sell")
async def ai_auto_sell(req: AutoSellRequest, request: Request):
    """Check positions for stop-loss/take-profit, create sell PROPOSAL (not executed).

    P0-2 fix: Returns a proposal requiring user confirmation via /trade/confirm-proposal.
    """
    from backend.app.core.trade_proposal import create_proposal, format_proposal_response

    db = await get_db()
    cursor = await db.execute("SELECT * FROM positions WHERE type='stock'")
    rows = [dict(r) for r in await cursor.fetchall()]
    if not rows:
        return {"data": {"bought": [], "message": "当前无持仓"}}

    quotes = await _fetch_quotes([r["code"] for r in rows])
    proposed_sells: list[dict] = []

    for r in rows:
        q = quotes.get(r["code"], {})
        price = float(q.get("price") or 0.0)
        if price <= 0:
            continue
        cost = float(r["cost"])
        if cost <= 0:
            continue
        pct = (price - cost) / cost * 100

        reason = ""
        if pct <= -req.stop_loss_pct:
            reason = f"触发止损 {pct:.1f}%"
        elif pct >= req.take_profit_pct:
            reason = f"触发止盈 +{pct:.1f}%"
        if not reason:
            continue

        proposed_sells.append({
            "action": "sell",
            "code": r["code"],
            "name": r["name"],
            "qty": r["qty"],
            "price": round(price, 2),
            "amount": round(r["qty"] * price, 2),
            "pnl": round((price - cost) * r["qty"], 2),
            "reason": reason,
        })

    logger.info("trade.ai_sell_proposal", proposed=len(proposed_sells))

    # Audit log
    info = extract_request_info(request)
    await log_audit(
        action="trade.ai_auto_sell.proposal",
        target="portfolio",
        detail={"stop_loss_pct": req.stop_loss_pct, "take_profit_pct": req.take_profit_pct, "proposed": proposed_sells},
        **info,
    )

    # Create proposal (NOT executing trades)
    proposal = create_proposal(
        sells=proposed_sells,
        buys=[],
    )
    return format_proposal_response(proposal)


@router.post("/trade/confirm-proposal")
@_serialized_trade
async def confirm_proposal(body: dict, request: Request):
    """Confirm and execute a trade proposal.

    Required: {"proposal_id": "xxx", "confirmed": true}
    Optional: {"selected_codes": ["600519", ...]} to execute only a subset.
    """
    from backend.app.core.trade_proposal import consume_proposal

    proposal_id = body.get("proposal_id", "")
    confirmed = body.get("confirmed", False)
    selected_codes = body.get("selected_codes", [])

    if not confirmed:
        return {"data": {"executed": [], "message": "用户未确认，取消执行"}}

    proposal = consume_proposal(proposal_id)
    if not proposal:
        return {"data": {"executed": [], "message": "提案不存在或已过期，请重新生成"}}

    db = await get_db()
    cash = await _get_cash(db)
    executed: list[dict] = []
    failed: list[dict] = []

    # Execute sells
    for s in proposal["sells"]:
        if selected_codes and s["code"] not in selected_codes:
            continue
        code = s["code"]
        qty = s["qty"]
        price = s["price"]
        amount = qty * price

        cursor = await db.execute(
            "SELECT id, qty, cost FROM positions WHERE code=? AND type='stock'", (code,)
        )
        pos = await cursor.fetchone()
        if not pos:
            failed.append({"action": "sell", "code": code, "error": "持仓不存在"})
            continue

        pnl = (price - pos["cost"]) * qty
        remain = pos["qty"] - qty
        if remain <= 1e-9:
            await db.execute("DELETE FROM positions WHERE id=?", (pos["id"],))
        else:
            await db.execute("UPDATE positions SET qty=? WHERE id=?", (remain, pos["id"]))

        cash += amount
        await _set_cash(db, cash)
        await db.execute(
            "INSERT INTO trade_log (code, name, type, action, qty, price, amount, note) VALUES (?,?,?,?,?,?,?,?)",
            (code, s.get("name", ""), "stock", "sell", qty, price, amount, f"AI清仓确认:{s.get('reason', '')}"),
        )
        executed.append({"action": "sell", "code": code, "qty": qty, "price": price, "pnl": round(pnl, 2)})

    # Execute buys
    for b in proposal["buys"]:
        if selected_codes and b["code"] not in selected_codes:
            continue
        code = b["code"]
        name = b.get("name", "")
        qty = b["qty"]
        price = b["price"]
        amount = qty * price

        if amount > cash + 1e-6:
            failed.append({"action": "buy", "code": code, "error": "资金不足"})
            continue

        cursor = await db.execute(
            "SELECT id, qty, cost FROM positions WHERE code=? AND type='stock'", (code,)
        )
        existing = await cursor.fetchone()
        if existing:
            new_qty = existing["qty"] + qty
            new_cost = (existing["cost"] * existing["qty"] + price * qty) / new_qty
            await db.execute(
                "UPDATE positions SET qty=?, cost=? WHERE id=?",
                (new_qty, new_cost, existing["id"]),
            )
        else:
            await db.execute(
                "INSERT INTO positions (code, name, type, qty, cost) VALUES (?,?,?,?,?)",
                (code, name, "stock", qty, price),
            )
        cash -= amount
        await _set_cash(db, cash)
        await db.execute(
            "INSERT INTO trade_log (code, name, type, action, qty, price, amount, note) VALUES (?,?,?,?,?,?,?,?)",
            (code, name, "stock", "buy", qty, price, amount, f"AI建仓确认:{b.get('reason', '')}"),
        )
        executed.append({"action": "buy", "code": code, "qty": qty, "price": price, "amount": round(amount, 2)})

    await db.commit()

    # Audit log
    info = extract_request_info(request)
    await log_audit(
        action="trade.proposal.confirmed",
        target=proposal_id,
        detail={"executed": executed, "failed": failed},
        **info,
    )

    return {"data": {
        "executed": executed,
        "failed": failed,
        "cash": round(cash, 2),
        "message": f"确认执行完成: {len(executed)}笔成功, {len(failed)}笔失败",
    }}


def _get_cache():
    from backend.app.deps import get_cache
    return get_cache()


# --- Watchlist ---

def _is_fund_code(code: str) -> bool:
    """Check if code is an OTC fund (not exchange-traded ETF)."""
    raw = code.replace("sh", "").replace("sz", "")
    return raw.startswith(("0", "2", "3")) or (raw.startswith("1") and not raw.startswith(("15", "16")))


@router.get("/watchlist")
async def get_watchlist():
    db = await get_db()
    cursor = await db.execute("SELECT * FROM watchlist ORDER BY added_at DESC")
    rows = await cursor.fetchall()
    items = [dict(r) for r in rows]

    # Enrich with real-time quotes (reuses 10s shared cache)
    if items:
        stock_items = [it for it in items if not _is_fund_code(it["code"])]
        fund_items = [it for it in items if _is_fund_code(it["code"])]

        if stock_items:
            quotes = await _fetch_quotes([it["code"] for it in stock_items])
            for it in stock_items:
                it.update(quotes.get(it["code"], {}))

        if fund_items:
            fund_navs = await _fetch_fund_nav([it["code"] for it in fund_items])
            for it in fund_items:
                raw = it["code"].replace("sh", "").replace("sz", "")
                it.update(fund_navs.get(raw, {}))

    return {"data": items}


@router.post("/watchlist/add")
async def add_watch(code: str, name: str = "", asset_type: str = "stock", request: Request = None):
    db = await get_db()
    try:
        await db.execute(
            "INSERT INTO watchlist (code, name, type) VALUES (?,?,?)",
            (code, name, asset_type),
        )
        await db.commit()
    except aiosqlite.IntegrityError:
        return {"ok": False, "message": "Already in watchlist"}
    except Exception as e:
        logger.warning("watchlist.add_failed", code=code, error=str(e))
        return {"ok": False, "message": "Failed to add to watchlist"}

    if request:
        info = extract_request_info(request)
        await log_audit(
            action="watchlist.add",
            target=code,
            detail={"name": name, "type": asset_type},
            **info,
        )

    return {"ok": True}


@router.post("/watchlist/remove")
async def remove_watch(code: str, request: Request = None):
    db = await get_db()
    await db.execute("DELETE FROM watchlist WHERE code=?", (code,))
    await db.commit()

    if request:
        info = extract_request_info(request)
        await log_audit(
            action="watchlist.remove",
            target=code,
            **info,
        )

    return {"ok": True}
