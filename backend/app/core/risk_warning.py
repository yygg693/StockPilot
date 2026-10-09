"""Risk warning system — generates contextual risk warnings for the UI.

Categories:
1. Market disclaimer — always shown
2. Suitability warnings — if investor profile mismatches positions
3. Position warnings — concentration, stop-loss proximity, drawdown
4. Account warnings — daily trade limit, cash ratio
"""
from __future__ import annotations

from backend.app.core.logging import get_logger
from backend.app.core.suitability import (
    check_product_suitability,
    get_product_grade,
    load_profile,
)

logger = get_logger("risk_warning")


# ---- Warning types ----

WARNING_LEVELS = {"info": 0, "warning": 1, "danger": 2, "critical": 3}


def _make_warning(level: str, category: str, title: str, detail: str) -> dict:
    return {
        "level": level,
        "category": category,
        "title": title,
        "detail": detail,
    }


# ---- Static disclaimers ----

MARKET_DISCLAIMER = _make_warning(
    "info",
    "disclaimer",
    "投资风险提示",
    "投资有风险，入市需谨慎。本平台提供的所有分析、信号、建议仅供参考，"
    "不构成投资建议。过往业绩不代表未来表现，投资者应根据自身风险承受能力"
    "做出独立决策，并对自己的投资行为负责。",
)

LEVERAGE_WARNING = _make_warning(
    "warning",
    "disclaimer",
    "杠杆交易风险",
    "本平台不支持杠杆交易。如使用外部杠杆工具，请知悉杠杆会放大盈利和亏损，"
    "可能导致超出本金的损失。",
)


# ---- Dynamic warnings ----

async def generate_warnings(account: dict, positions: list[dict] | None = None) -> list[dict]:
    """Generate all applicable risk warnings for the current portfolio.

    Args:
        account: dict with cash, total_assets, initial_cash, positions
        positions: optional override for account.get("positions")

    Returns:
        List of warning dicts, sorted by severity (critical first).
    """
    warnings: list[dict] = []
    positions = positions or account.get("positions", [])
    total_assets = account.get("total_assets", account.get("cash", 0))
    initial_cash = account.get("initial_cash", total_assets)
    cash = account.get("cash", 0)

    # 1. Always include market disclaimer
    warnings.append(MARKET_DISCLAIMER)

    # 2. Suitability warnings
    profile = await load_profile()
    if profile and profile.score > 0:
        # Check each position against investor risk level
        for p in positions:
            code = p.get("code", "")
            name = p.get("name", "")
            grade = get_product_grade(code, name)
            check = check_product_suitability(profile.risk_level, grade)
            if not check["suitable"]:
                warnings.append(_make_warning(
                    "danger",
                    "suitability",
                    f"适当性不匹配: {name or code}",
                    check["warning"],
                ))
    else:
        # No assessment yet
        warnings.append(_make_warning(
            "warning",
            "suitability",
            "未完成风险测评",
            "您尚未完成投资者适当性评估，建议先完成风险测评再进行投资操作。"
            "请前往「设置 > 风险测评」完成评估。",
        ))

    # 3. Position concentration warnings
    if positions and total_assets > 0:
        for p in positions:
            code = p.get("code", "")
            name = p.get("name", code)
            qty = p.get("qty", 0)
            price = p.get("price", p.get("cost", 0))
            value = qty * price
            pct = value / total_assets * 100
            if pct > 30:
                warnings.append(_make_warning(
                    "danger",
                    "concentration",
                    f"仓位过度集中: {name}",
                    f"{name}占组合{pct:.1f}%，超过30%集中度阈值，"
                    f"建议分散投资降低单一标的风险。",
                ))
            elif pct > 20:
                warnings.append(_make_warning(
                    "warning",
                    "concentration",
                    f"仓位偏高: {name}",
                    f"{name}占组合{pct:.1f}%，建议关注集中度风险。",
                ))

    # 4. Stop-loss proximity warnings
    for p in positions:
        code = p.get("code", "")
        name = p.get("name", code)
        cost = p.get("cost", 0)
        price = p.get("price", 0)
        if cost > 0 and price > 0:
            pnl_pct = (price / cost - 1) * 100
            if pnl_pct <= -5:
                warnings.append(_make_warning(
                    "danger",
                    "stop_loss",
                    f"接近止损: {name}",
                    f"{name}当前亏损{pnl_pct:.1f}%，接近-8%止损线，"
                    f"请关注是否需要止损操作。",
                ))
            elif pnl_pct <= -3:
                warnings.append(_make_warning(
                    "warning",
                    "stop_loss",
                    f"持仓浮亏: {name}",
                    f"{name}当前亏损{pnl_pct:.1f}%，请注意风险。",
                ))

    # 5. Account-level warnings
    if initial_cash > 0 and total_assets > 0:
        total_return = (total_assets / initial_cash - 1) * 100
        if total_return <= -10:
            warnings.append(_make_warning(
                "critical",
                "drawdown",
                "组合大幅亏损",
                f"组合总收益{total_return:.1f}%，已超过-10%亏损阈值，"
                f"建议暂停新增买入，审视持仓结构。",
            ))
        elif total_return <= -5:
            warnings.append(_make_warning(
                "warning",
                "drawdown",
                "组合亏损",
                f"组合总收益{total_return:.1f}%，请注意控制风险。",
            ))

    # Cash ratio warning
    if total_assets > 0:
        cash_ratio = cash / total_assets * 100
        if cash_ratio < 5:
            warnings.append(_make_warning(
                "warning",
                "cash_ratio",
                "现金比例过低",
                f"现金仅占组合{cash_ratio:.1f}%，应对突发风险的能力不足，"
                f"建议保留至少10%的现金仓位。",
            ))

    # 6. Add leverage warning if any position looks leveraged
    for p in positions:
        name = p.get("name", "")
        if any(kw in name for kw in ("杠杆", "融资", "融券")):
            warnings.append(LEVERAGE_WARNING)
            break

    # Sort by severity (critical first)
    warnings.sort(key=lambda w: -WARNING_LEVELS.get(w["level"], 0))

    return warnings


def get_trade_confirmation_warning(action: str, code: str, name: str, amount: float) -> str:
    """Generate a confirmation warning string for a specific trade.

    Used in the trade confirmation dialog.
    """
    grade = get_product_grade(code, name)
    grade_name = {
        "R1": "低风险", "R2": "中低风险", "R3": "中风险",
        "R4": "中高风险", "R5": "高风险",
    }.get(grade, "未知")

    return (
        f"您即将{('买入' if action == 'buy' else '卖出')}{name or code}，"
        f"金额约{amount:.0f}元。该产品风险等级为{grade}({grade_name})。"
        f"投资有风险，请确认您已充分了解该投资的风险特征。"
    )
