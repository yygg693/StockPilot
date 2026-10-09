"""
回测模块（Backtest）：对单标的按策略做历史回测。
支持策略：
  - ma_cross : 双均线（快线上穿慢线持仓，下穿空仓），参数 fast/slow
  - macd     : MACD（DIF 在 DEA 上方持仓，否则空仓）
输出：资金曲线（策略 vs 买入持有）、交易明细、绩效指标。
纯多头上证（不做空）。

真实成本模型（A股）：
  - 佣金：commission（默认万2.5=0.00025），单笔最低 commission_min=5 元（双边收取）
  - 印花税：stamp（默认万5=0.0005），仅卖出收取（2023-08-28 起减半）
  - 过户费：transfer（默认万0.1=0.00001），双边收取
  - 滑点：slippage（默认千1=0.001），买卖各单边
风控：
  - 止损：stop_loss（默认 0=关闭），持仓中收盘跌破 买入价*(1-stop_loss) 即止损平仓
  - 仓位：全仓（信号出现即用可用资金按 100 股整数倍买入）
"""
from backend.data import market
from backend.indicators import mytt


STRATEGIES = {
    "ma_cross": "双均线交叉（MA fast/slow）",
    "macd": "MACD（DIF 在 DEA 上方持仓）",
}


def _max_drawdown(eq):
    peak = eq[0]
    mdd = 0.0
    for v in eq:
        if v > peak:
            peak = v
        dd = (v - peak) / peak
        if dd < mdd:
            mdd = dd
    return mdd


def _positions(closes, strategy, params):
    """返回与 closes 等长的仓位序列（1=持仓, 0=空仓）。position[i] 表示第 i 根 K线收盘后的状态。"""
    n = len(closes)
    pos = [0] * n
    if strategy == "macd":
        dif, dea, _ = mytt.MACD(closes)
        for i in range(n):
            if dif.iloc[i] is not None and dea.iloc[i] is not None and dif.iloc[i] > dea.iloc[i]:
                pos[i] = 1
    else:  # ma_cross
        fast = int(params.get("fast", 5))
        slow = int(params.get("slow", 20))
        ma_f = mytt.MA(closes, fast)
        ma_s = mytt.MA(closes, slow)
        for i in range(n):
            a, b = ma_f.iloc[i], ma_s.iloc[i]
            if a is not None and b is not None and a > b:
                pos[i] = 1
    return pos


def backtest(code, strategy="ma_cross", params=None, limit=250, asset_type=None):
    params = params or {}
    strategy = (strategy or "ma_cross").lower()
    if strategy not in STRATEGIES:
        return {"error": f"未知策略: {strategy}", "strategies": STRATEGIES}
    asset_type = asset_type or market.classify_code(code)
    kd = market.get_kline(code, asset_type, limit=limit)
    rows = kd.get("rows") or []
    if len(rows) < 30:
        return {"error": "K线数据不足（需≥30根），无法回测", "rows": len(rows)}
    closes = [float(r["close"]) for r in rows]
    dates = [r["date"] for r in rows]
    pos = _positions(closes, strategy, params)

    # ---- 成本与风控参数（A股真实假设）----
    commission = float(params.get("commission", 0.00025))
    commission_min = float(params.get("commission_min", 5.0))
    stamp = float(params.get("stamp", 0.0005))
    transfer = float(params.get("transfer", 0.00001))
    slippage = float(params.get("slippage", 0.001))
    stop_loss = float(params.get("stop_loss", 0.0))   # 0 = 关闭
    init_capital = float(params.get("capital", 500000.0))

    LOT = 100.0

    def _buy_cost(price, qty):
        c = max(commission_min, price * qty * commission)
        t = price * qty * transfer
        return c, t

    def _sell_cost(price, qty):
        c = max(commission_min, price * qty * commission)
        s = price * qty * stamp
        t = price * qty * transfer
        return c, s, t

    # ---- 买入持有（计入成本，用于公平对比）----
    hold_buy_px = closes[0] * (1 + slippage)
    hqty = int(init_capital // (hold_buy_px * LOT)) * int(LOT)
    if hqty < LOT:
        hqty = 0.0
    hcost = hqty * hold_buy_px
    hc, htr = _buy_cost(hold_buy_px, hqty)
    hold_cash = init_capital - (hcost + hc + htr)
    hold_shares = hqty
    hold_sell_px = closes[-1] * (1 - slippage)
    hpc, hps, hpt = _sell_cost(hold_sell_px, hold_shares)
    hold_final = hold_cash + (hold_shares * hold_sell_px) - hpc - hps - hpt
    hold_return = hold_final / init_capital - 1 if init_capital else 0.0

    # ---- 策略模拟（净/毛并行，毛=无成本，便于对比摩擦损耗）----
    cash = init_capital
    shares = 0.0
    gcash = init_capital      # 毛收益资金（无成本）
    gshares = 0.0
    in_pos = False
    entry_price = 0.0
    entry_date = None
    equity = [init_capital]            # 第0根（期初）
    trades = []
    cost_total = 0.0
    stop_hits = 0

    def _do_buy(px, date):
        nonlocal cash, shares, gcash, gshares, in_pos, entry_price, entry_date, cost_total
        exec_px = px * (1 + slippage)
        qty = int(cash // (exec_px * LOT)) * int(LOT)
        if qty < LOT:
            return False
        cost = qty * exec_px
        c, t = _buy_cost(exec_px, qty)
        total = cost + c + t
        if total > cash:
            qty -= LOT
            if qty < LOT:
                return False
            cost = qty * exec_px
            c, t = _buy_cost(exec_px, qty)
            total = cost + c + t
        # 净
        cash -= total
        cost_total += c + t
        shares = qty
        # 毛（同数量，无成本/滑点）
        gcash -= qty * px
        gshares = qty
        in_pos = True
        entry_price = exec_px
        entry_date = date
        trades.append({"type": "BUY", "date": date, "price": round(px, 3), "pnl_pct": None})
        return True

    def _do_sell(px, date, note=""):
        nonlocal cash, shares, gcash, gshares, in_pos, entry_price, cost_total
        if shares <= 0:
            return False
        qty = shares
        exec_px = px * (1 - slippage)
        proceeds = qty * exec_px
        c, s, t = _sell_cost(exec_px, qty)
        cash += proceeds - c - s - t
        cost_total += c + s + t
        pnl = (exec_px / entry_price - 1) if entry_price else 0.0
        # 毛
        gcash += qty * px
        gshares = 0.0
        trades.append({"type": "SELL", "date": date, "price": round(px, 3),
                       "pnl_pct": round(pnl * 100, 2), "note": note})
        shares = 0.0
        in_pos = False
        entry_price = 0.0
        return True

    for i in range(1, len(closes)):
        prev, cur = pos[i - 1], pos[i]
        if in_pos and stop_loss > 0 and closes[i] <= entry_price * (1 - stop_loss):
            _do_sell(closes[i], dates[i], note="止损")
            stop_hits += 1
        elif cur == 1 and prev == 0 and not in_pos:
            _do_buy(closes[i - 1], dates[i - 1])
        elif cur == 0 and prev == 1 and in_pos:
            _do_sell(closes[i - 1], dates[i - 1], note="信号离场")
        eq_now = cash + shares * closes[i]
        equity.append(eq_now)

    if in_pos:
        _do_sell(closes[-1], dates[-1], note="期末平仓")

    # ---- 绩效指标 ----
    total_return = equity[-1] / init_capital - 1
    gross_final = gcash + gshares * closes[-1]
    gross_return = gross_final / init_capital - 1
    mdd = _max_drawdown(equity)
    wins = 0
    roundtrips = 0
    for t in trades:
        if t["type"] == "SELL" and t.get("pnl_pct") is not None:
            roundtrips += 1
            if t["pnl_pct"] > 0:
                wins += 1
    win_rate = (wins / roundtrips) if roundtrips else 0.0
    years = len(closes) / 252.0
    annual = ((1 + total_return) ** (1 / years) - 1) if (years > 0 and (1 + total_return) > 0) else 0.0

    name = (market.get_quote(code, asset_type) or {}).get("name") or code
    equity_out = [{
        "date": dates[i],
        "strategy": round(equity[i] / init_capital, 4),
        "hold": round((hold_cash + hold_shares * closes[i]) / init_capital, 4),
    } for i in range(len(dates))]

    return {
        "code": code, "name": name, "type": asset_type,
        "strategy": strategy, "strategy_name": STRATEGIES[strategy],
        "params": {
            "fast": params.get("fast", 5), "slow": params.get("slow", 20)
        } if strategy == "ma_cross" else {"macd": True},
        "cost": {
            "commission": commission, "commission_min": commission_min,
            "stamp": stamp, "transfer": transfer, "slippage": slippage,
            "stop_loss": stop_loss, "capital": init_capital,
        },
        "equity": equity_out,
        "trades": trades,
        "metrics": {
            "total_return": round(total_return * 100, 2),       # 净收益（扣成本）
            "gross_return": round(gross_return * 100, 2),        # 毛收益（未扣成本）
            "cost_total": round(cost_total, 2),                 # 总成本（元）
            "annual_return": round(annual * 100, 2),
            "max_drawdown": round(mdd * 100, 2),
            "win_rate": round(win_rate * 100, 2),
            "roundtrips": roundtrips,
            "num_trades": len([t for t in trades if t["type"] == "BUY"]),
            "stop_loss_hits": stop_hits,
            "vs_hold": round((total_return - hold_return) * 100, 2),
            "hold_return": round(hold_return * 100, 2),
            "final_equity": round(equity[-1], 2),
        },
    }
