"""AI tools for function calling - lets AI query data autonomously."""
from __future__ import annotations

import json

from backend.app.core.http_client import get_http_client
from backend.app.core.logging import get_logger
from backend.app.services.ai_context import get_trade_db, get_watchlist_store
from backend.app.services.data_tencent import fetch_quote_batch

logger = get_logger("ai.tools")

# Tool definitions (OpenAI function calling format)
TOOL_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "get_stock_quote",
            "description": "获取股票实时行情（价格、涨跌幅、成交量、市盈率等）。输入股票代码如 sh600519、sz000858。",
            "parameters": {
                "type": "object",
                "properties": {
                    "code": {"type": "string", "description": "股票代码，如 sh600519、sz000858"}
                },
                "required": ["code"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_my_positions",
            "description": "查看用户当前的持仓和可用资金。不需要参数。",
            "parameters": {
                "type": "object",
                "properties": {}
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_my_watchlist",
            "description": "查看用户的自选股列表。不需要参数。",
            "parameters": {
                "type": "object",
                "properties": {}
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_market_overview",
            "description": "获取大盘指数（上证、深证、创业板）的实时行情。不需要参数。",
            "parameters": {
                "type": "object",
                "properties": {}
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_fund_info",
            "description": "获取基金的基本信息（净值、收益率、经理、持仓等）。输入基金代码如 005827。",
            "parameters": {
                "type": "object",
                "properties": {
                    "code": {"type": "string", "description": "基金代码，如 005827、161725"}
                },
                "required": ["code"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "execute_trade",
            "description": "执行买入或卖出操作。仅在用户明确要求交易时调用。",
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {"type": "string", "enum": ["buy", "sell"], "description": "买入或卖出"},
                    "code": {"type": "string", "description": "股票/基金代码"},
                    "name": {"type": "string", "description": "名称"},
                    "amount": {"type": "number", "description": "金额（元）或数量（股）"}
                },
                "required": ["action", "code", "amount"]
            }
        }
    },
]


async def execute_tool(name: str, arguments: dict) -> str:
    """Execute a tool and return result as string."""
    try:
        if name == "get_stock_quote":
            code = arguments.get("code", "")
            client = get_http_client()
            quotes = await fetch_quote_batch(client, [code])
            q = quotes.get(code)
            if q:
                return json.dumps(q, ensure_ascii=False)
            return f"未找到 {code} 的行情数据"

        elif name == "get_my_positions":
            db = await get_trade_db()
            return json.dumps({
                "cash": db["cash"],
                "positions": db["positions"],
                "total_positions": len(db["positions"]),
            }, ensure_ascii=False)

        elif name == "get_my_watchlist":
            wl = await get_watchlist_store()
            return json.dumps(wl, ensure_ascii=False)

        elif name == "get_market_overview":
            client = get_http_client()
            codes = ["sh000001", "sz399001", "sz399006"]
            quotes = await fetch_quote_batch(client, codes)
            result = []
            for c in codes:
                q = quotes.get(c)
                if q:
                    result.append(q)
            return json.dumps(result, ensure_ascii=False)

        elif name == "get_fund_info":
            code = arguments.get("code", "")
            client = get_http_client()
            r = await client.get(
                f"https://fund.eastmoney.com/pingzhongdata/{code}.js",
                headers={"Referer": "https://fund.eastmoney.com", "User-Agent": "Mozilla/5.0"},
                timeout=10.0,
            )
            text = r.text
            import re
            info = {"code": code}
            m = re.search(r'var fS_name = "(.*?)"', text)
            if m:
                info["name"] = m.group(1)
            m = re.search(r'var syl_1n="(.*?)"', text)
            if m:
                info["return_1y"] = m.group(1)
            m = re.search(r'var syl_6y="(.*?)"', text)
            if m:
                info["return_6m"] = m.group(1)
            m = re.search(r'var syl_3y="(.*?)"', text)
            if m:
                info["return_3m"] = m.group(1)
            # Manager
            mgr_idx = text.find("Data_currentFundManager")
            if mgr_idx != -1:
                nm = re.search(r'"name":"(.*?)"', text[mgr_idx:mgr_idx+500])
                if nm:
                    info["manager"] = nm.group(1)
            return json.dumps(info, ensure_ascii=False)

        elif name == "execute_trade":
            action = arguments.get("action")
            code = arguments.get("code", "")
            name_str = arguments.get("name", "")
            amount = float(arguments.get("amount", 0))

            # Write to SQLite (unified storage - was in-memory before P0-3 fix)
            from backend.app.db.session import get_db as get_sqlite_db
            INITIAL_CASH = 1_000_000.0
            sdb = await get_sqlite_db()

            # Ensure account exists
            await sdb.execute(
                "INSERT OR IGNORE INTO account (id, cash, initial_cash) VALUES (1, ?, ?)",
                (INITIAL_CASH, INITIAL_CASH),
            )

            # Get current cash
            cursor = await sdb.execute("SELECT cash FROM account WHERE id=1")
            row = await cursor.fetchone()
            cash = float(row["cash"]) if row else INITIAL_CASH

            asset_type = "fund" if len(code) == 6 and code[0] != "6" else "stock"

            if action == "buy":
                if amount > cash:
                    return json.dumps({"success": False, "error": "资金不足"}, ensure_ascii=False)

                # Fetch real-time price to calculate qty
                client = get_http_client()
                quotes = await fetch_quote_batch(client, [code])
                q = quotes.get(code, {})
                price = float(q.get("price", 0)) if q else 0
                if price <= 0:
                    price = amount  # fallback: treat amount as total cost, qty=1
                    qty = 1
                else:
                    qty = amount / price

                # Check existing position
                cursor = await sdb.execute(
                    "SELECT id, qty, cost FROM positions WHERE code=? AND type=?",
                    (code, asset_type),
                )
                existing = await cursor.fetchone()
                if existing:
                    new_qty = existing["qty"] + qty
                    new_cost = (existing["cost"] * existing["qty"] + price * qty) / new_qty
                    await sdb.execute(
                        "UPDATE positions SET qty=?, cost=? WHERE id=?",
                        (new_qty, new_cost, existing["id"]),
                    )
                else:
                    await sdb.execute(
                        "INSERT INTO positions (code, name, type, qty, cost) VALUES (?,?,?,?,?)",
                        (code, name_str, asset_type, qty, price),
                    )

                cash -= amount
                await sdb.execute(
                    "UPDATE account SET cash=?, updated_at=datetime('now','localtime') WHERE id=1",
                    (round(cash, 2),),
                )
                await sdb.execute(
                    "INSERT INTO trade_log (code, name, type, action, qty, price, amount, note) VALUES (?,?,?,?,?,?,?,?)",
                    (code, name_str, asset_type, "buy", qty, price, amount, "AI execute_trade"),
                )
                await sdb.commit()
                return json.dumps({"success": True, "message": f"买入成功: {name_str} {amount:.0f}元"}, ensure_ascii=False)

            elif action == "sell":
                # Find position
                cursor = await sdb.execute(
                    "SELECT id, qty, cost FROM positions WHERE code=? AND type=?",
                    (code, asset_type),
                )
                pos = await cursor.fetchone()
                if not pos:
                    return json.dumps({"success": False, "error": "无持仓"}, ensure_ascii=False)

                # Fetch real-time price
                client = get_http_client()
                quotes = await fetch_quote_batch(client, [code])
                q = quotes.get(code, {})
                price = float(q.get("price", 0)) if q else 0
                if price <= 0:
                    price = amount  # fallback
                    qty = pos["qty"]
                else:
                    qty = amount / price

                if qty > pos["qty"]:
                    qty = pos["qty"]

                remain = pos["qty"] - qty
                if remain <= 1e-9:
                    await sdb.execute("DELETE FROM positions WHERE id=?", (pos["id"],))
                else:
                    await sdb.execute("UPDATE positions SET qty=? WHERE id=?", (remain, pos["id"]))

                sell_amount = qty * price
                pnl = (price - pos["cost"]) * qty
                cash += sell_amount
                await sdb.execute(
                    "UPDATE account SET cash=?, updated_at=datetime('now','localtime') WHERE id=1",
                    (round(cash, 2),),
                )
                await sdb.execute(
                    "INSERT INTO trade_log (code, name, type, action, qty, price, amount, note) VALUES (?,?,?,?,?,?,?,?)",
                    (code, name_str, asset_type, "sell", qty, price, sell_amount, f"AI execute_trade, pnl={pnl:.2f}"),
                )
                await sdb.commit()
                return json.dumps({"success": True, "message": f"卖出成功: {name_str} {sell_amount:.0f}元, 盈亏{pnl:.0f}元"}, ensure_ascii=False)

        return f"未知工具: {name}"
    except Exception as e:
        logger.error("tool.exec_failed", tool=name, error=str(e))
        return f"工具执行失败: {str(e)}"
