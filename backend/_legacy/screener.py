"""
选股模块（Screener）：在给定股票池上按策略筛选，输出命中标的 + 命中理由。
内置策略：
  - value   : 低估价值（低 PE + 低 PB，且盈利为正）
  - momentum: 强势动量（当日涨幅居前 + 换手活跃 + 有成交额）
  - golden  : 技术金叉（MA 多头排列 + MACD 金叉区，需逐标的拉 K线）
股票池 universe：watch / hs300 / all
全A(all) 用 spot 行情列表做估值/动量筛选（一次请求，快）；金叉策略对全A 先估值预筛再取流动性前 N 名拉 K线，控制请求量。
"""
from backend import universe as universe_mod
from backend.data import market
from backend.indicators import mytt


STRATEGIES = {
    "value": "低估价值（低 PE + 低 PB）",
    "momentum": "强势动量（涨幅居前 + 活跃）",
    "golden": "技术金叉（MA 多头 + MACD 金叉）",
}


def _golden_check(code):
    """对单标的拉 K线，判断是否 MA 多头排列 + MACD 金叉区。返回 (hit, reason)。"""
    try:
        kd = market.get_kline(code, "stock", limit=60)
        rows = kd.get("rows") or []
        if len(rows) < 30:
            return False, "数据不足"
        ind = mytt.compute_all(rows)
        sig = {s[0]: s[1] for s in ind.get("signals", [])}
        ma_bull = sig.get("均线", "").startswith("多头排列")
        macd_gold = sig.get("MACD", "").startswith("DIF 在 DEA 上方")
        if ma_bull and macd_gold:
            return True, "MA 多头排列 + MACD 金叉区"
        return False, ("均线未多头" if not ma_bull else "MACD 未金叉")
    except Exception as e:  # noqa
        return False, f"K线获取失败: {e}"


def screen(strategy="value", universe="all", params=None):
    params = params or {}
    strategy = (strategy or "value").lower()
    universe = (universe or "all").lower()

    # 取股票池
    if strategy == "golden" and universe == "all":
        # 全A 金叉：先按快照预筛「盈利 + 有成交额」的活跃股，再取流动性前 N 名拉 K线。
        # 既显著扩大覆盖面（默认 200，可调 top_n），又避免对 5200 只逐一拉 K线拖慢请求。
        # 不硬性要求"当日上涨"——跌市里也会有很多正在筑底/金叉的标的，金叉信号本身由 K线判定。
        spot = universe_get_spot()
        if spot is None:
            codes = universe_mod.get_universe("hs300")
        else:
            cand = [s for s in spot
                    if (s.get("pe") or 0) > 0 and (s.get("pb") or 0) > 0
                    and (s.get("amount") or 0) > 0]
            cand.sort(key=lambda s: (s.get("amount") or 0), reverse=True)
            top = cand[: int(params.get("top_n", 200))]
            codes = [{"code": s["code"], "name": s["name"]} for s in top]
    else:
        codes = universe_mod.get_universe(universe)

    matches = []
    scanned = len(codes)

    if strategy == "value":
        pe_max = float(params.get("pe_max", 20))
        pb_max = float(params.get("pb_max", 3))
        # 全A 估值筛选必须有快照；快照未生成时提示先重建，避免逐只慢扫全市场
        if universe == "all" and universe_get_spot() is None:
            return {"error": "全A 估值快照尚未生成，请先在【选股】页点「重建快照」再跑全市场筛选。",
                    "strategy": strategy, "universe": universe, "scanned": 0, "count": 0, "matches": []}
        spot_map = {s["code"]: s for s in (universe_get_spot() or [])}
        for it in codes:
            q = spot_map.get(it["code"]) or _quote_fallback(it["code"])
            if not q:
                continue
            pe, pb = q.get("pe"), q.get("pb")
            if pe and pb and 0 < pe <= pe_max and 0 < pb <= pb_max:
                matches.append({
                    "code": it["code"], "name": it.get("name") or q.get("name") or it["code"],
                    "price": q.get("price"), "change_pct": q.get("change_pct"),
                    "pe": pe, "pb": pb,
                    "reason": f"PE={pe}≤{pe_max}，PB={pb}≤{pb_max}，估值偏低",
                })
    elif strategy == "momentum":
        # 需要涨幅数据：用 spot 列表（含涨跌幅）
        if universe == "all" and universe_get_spot() is None:
            return {"error": "全A 行情快照尚未生成，请先在【选股】页点「重建快照」再跑全市场筛选。",
                    "strategy": strategy, "universe": universe, "scanned": 0, "count": 0, "matches": []}
        spot = universe_get_spot()
        if spot is None:
            # 无 spot 时退化为对股票池逐个取行情（慢）
            spot_map = {}
            for it in codes:
                q = _quote_fallback(it["code"])
                if q:
                    spot_map[it["code"]] = q
        else:
            spot_map = {s["code"]: s for s in spot}
        # 计算涨幅阈值：取股票池内前 20% 分位
        chgs = [s.get("change_pct") for s in spot_map.values()
                if s.get("change_pct") is not None]
        if chgs:
            chgs.sort()
            thr = chgs[int(len(chgs) * 0.8)] if len(chgs) > 5 else 0
        else:
            thr = 0
        min_amount = float(params.get("min_amount", 1e8))  # 默认成交额≥1亿
        for it in codes:
            q = spot_map.get(it["code"])
            if not q:
                continue
            chg = q.get("change_pct")
            amt = q.get("amount") or 0
            if chg is not None and chg >= thr and amt >= min_amount:
                matches.append({
                    "code": it["code"], "name": it.get("name") or q.get("name") or it["code"],
                    "price": q.get("price"), "change_pct": chg,
                    "pe": q.get("pe"), "pb": q.get("pb"),
                    "reason": f"涨幅 {chg}% 居前（≥{round(thr,2)}%），成交额 {_fmt_amt(amt)}",
                })
    elif strategy == "golden":
        for it in codes:
            hit, reason = _golden_check(it["code"])
            if hit:
                q = _quote_fallback(it["code"]) or {}
                matches.append({
                    "code": it["code"], "name": it.get("name") or q.get("name") or it["code"],
                    "price": q.get("price"), "change_pct": q.get("change_pct"),
                    "reason": reason,
                })
    else:
        return {"error": f"未知策略: {strategy}", "strategies": STRATEGIES}

    # 排序：动量按涨幅、价值按 PE
    if strategy == "momentum":
        matches.sort(key=lambda m: (m.get("change_pct") or 0), reverse=True)
    elif strategy == "value":
        matches.sort(key=lambda m: (m.get("pe") or 1e9))

    return {
        "strategy": strategy,
        "strategy_name": STRATEGIES.get(strategy, strategy),
        "universe": universe,
        "scanned": scanned,
        "count": len(matches),
        "matches": matches[: int(params.get("limit", 50))],
    }


def universe_get_spot():
    """获取全A 行情/估值快照（用于估值/动量筛选与预筛）。"""
    return universe_mod.get_spot_snapshot()


def _quote_fallback(code):
    try:
        return market.get_quote(code, "stock")
    except Exception:  # noqa
        return None


def _fmt_amt(v):
    if v is None:
        return "-"
    if v >= 1e8:
        return f"{v/1e8:.1f}亿"
    if v >= 1e4:
        return f"{v/1e4:.0f}万"
    return str(v)
