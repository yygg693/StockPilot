"""
模拟盘（Paper Trading）：用 store 的 positions 表记录持仓，按实时行情计算浮动盈亏。
不做真实交易，仅用于策略验证与学习。
"""
from backend.db import store
from backend.data import market


def buy(code, qty, name=None, asset_type=None, price=None):
    """模拟买入。price 不传则取当前行情价。返回持仓记录。"""
    qty = float(qty)
    if qty <= 0:
        return {"ok": False, "error": "数量必须为正"}
    asset_type = asset_type or market.classify_code(code)
    if price is None:
        q = market.get_quote(code, asset_type)
        price = q.get("price")
        if name is None:
            name = q.get("name")
    if not price:
        return {"ok": False, "error": "无法获取买入价格"}
    if name is None:
        name = code
    store.buy_position(code, name, asset_type, qty, float(price))
    return {"ok": True, "code": code, "qty": qty, "price": float(price)}


def sell(code, qty, asset_type=None, price=None):
    """模拟卖出。price 不传则取当前行情价。"""
    qty = float(qty)
    if qty <= 0:
        return {"ok": False, "error": "数量必须为正"}
    asset_type = asset_type or market.classify_code(code)
    if price is None:
        q = market.get_quote(code, asset_type)
        price = q.get("price")
    if not price:
        return {"ok": False, "error": "无法获取卖出价格"}
    result = store.sell_position(code, asset_type, qty)
    if result is None:
        return {"ok": False, "error": "卖出数量超过当前持仓"}
    if not result:
        return {"ok": False, "error": "无该标的持仓"}
    return {"ok": True, "code": code, "qty": qty, "price": float(price)}


def positions_with_pnl():
    """列出全部持仓，并附实时盈亏。"""
    rows = store.list_positions()
    out = []
    total_cost = 0.0
    total_mv = 0.0
    for p in rows:
        code = p["code"]
        atype = p.get("type", "stock")
        qty = float(p["qty"])
        cost = float(p["cost"])
        try:
            q = market.get_quote(code, atype)
            price = q.get("price")
            pname = q.get("name") or p.get("name")
        except Exception:  # noqa
            price = None
            pname = p.get("name")
        mv = (price * qty) if price else None
        pnl = ((price - cost) * qty) if price else None
        pnl_pct = ((price / cost - 1) * 100) if (price and cost) else None
        cost_amt = cost * qty
        total_cost += cost_amt
        if mv is not None:
            total_mv += mv
        out.append({
            "code": code, "name": pname, "type": atype,
            "qty": qty, "cost": cost, "price": price,
            "market_value": round(mv, 2) if mv is not None else None,
            "pnl": round(pnl, 2) if pnl is not None else None,
            "pnl_pct": round(pnl_pct, 2) if pnl_pct is not None else None,
            "opened_at": p.get("opened_at"),
        })
    total_pnl = (total_mv - total_cost) if total_mv else None
    total_pnl_pct = ((total_mv / total_cost - 1) * 100) if (total_mv and total_cost) else None
    return {
        "positions": out,
        "summary": {
            "count": len(out),
            "total_cost": round(total_cost, 2),
            "total_market_value": round(total_mv, 2) if total_mv else None,
            "total_pnl": round(total_pnl, 2) if total_pnl is not None else None,
            "total_pnl_pct": round(total_pnl_pct, 2) if total_pnl_pct is not None else None,
        },
    }
