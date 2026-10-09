"""Unified risk management engine — single source of truth for all risk checks.

Consolidates the two previous RiskManager implementations:
- backend/app/trading/risk.py (event-driven, unused)
- backend/app/services/ai_signals.py (dict-based, actively used by AI)

This module provides a clean dict-based interface that works with both
the AI signal pipeline and the trade router.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from backend.app.core.logging import get_logger

logger = get_logger("risk")


@dataclass
class RiskLimits:
    """Configurable risk parameters — all in one place."""
    max_position_pct: float = 0.20          # Single stock max position % of total assets
    max_total_position_pct: float = 0.80    # Total invested % max
    max_total_positions: int = 10           # Max number of concurrent positions
    max_daily_trades: int = 10              # Max trades per day
    max_single_order_amount: float = 200_000.0  # Max amount per single order
    stop_loss_pct: float = -8.0             # Stop loss trigger (negative %)
    take_profit_pct: float = 20.0           # Take profit trigger (positive %)
    max_drawdown_pct: float = -15.0         # Max drawdown before halting (negative %)
    chase_high_pct: float = 10.0            # Reject buy if stock up > this % today


@dataclass
class RiskCheckResult:
    """Result of a risk check."""
    allowed: bool
    reason: str = ""
    adjusted_qty: float = 0.0
    adjusted_amount: float = 0.0


class RiskManager:
    """Unified pre-trade and post-trade risk engine.

    Usage:
        rm = get_risk_manager()
        result = rm.check_buy(code, amount, account_dict)
        if result.allowed:
            rm.record_trade()
    """

    def __init__(self, limits: RiskLimits | None = None):
        self.limits = limits or RiskLimits()
        self._daily_trades: int = 0
        self._daily_date: str = datetime.now().strftime("%Y-%m-%d")
        self._peak_value: float = 0.0

    def _reset_daily(self) -> None:
        """Reset daily counters if date changed."""
        today = datetime.now().strftime("%Y-%m-%d")
        if self._daily_date != today:
            self._daily_date = today
            self._daily_trades = 0

    # ---- Pre-trade checks ----

    def check_buy(
        self,
        code: str,
        amount: float,
        account: dict,
        change_pct: float = 0.0,
    ) -> RiskCheckResult:
        """Validate a buy order against all risk rules.

        Args:
            code: Stock code
            amount: Order amount in yuan
            account: Dict with keys: cash, total_assets, positions (list of dicts),
                     initial_cash (optional)
            change_pct: Today's price change % (for chase-high check)

        Returns:
            RiskCheckResult with allowed, reason, and adjusted values.
        """
        self._reset_daily()

        total_assets = account.get("total_assets", account.get("cash", 0))
        cash = account.get("cash", 0)
        positions = account.get("positions", [])

        # 1. Daily trade limit
        if self._daily_trades >= self.limits.max_daily_trades:
            return RiskCheckResult(False, f"今日交易次数已达上限({self.limits.max_daily_trades}次)")

        # 2. Max positions count
        pos_codes = {p.get("code") for p in positions}
        if code not in pos_codes and len(positions) >= self.limits.max_total_positions:
            return RiskCheckResult(False, f"持仓数量已达上限({self.limits.max_total_positions}只)")

        # 3. Single order amount limit
        if amount > self.limits.max_single_order_amount:
            return RiskCheckResult(
                False,
                f"单笔金额{amount:.0f}超过限额{self.limits.max_single_order_amount:.0f}",
            )

        # 4. Chase-high check
        if change_pct > self.limits.chase_high_pct:
            return RiskCheckResult(
                False,
                f"今日涨幅{change_pct:.1f}%超过追高阈值{self.limits.chase_high_pct:.0f}%",
            )

        # 5. Position concentration limit
        max_amount = total_assets * self.limits.max_position_pct
        existing_value = 0.0
        for p in positions:
            if p.get("code") == code:
                existing_value = p.get("qty", 0) * p.get("price", p.get("cost", 0))
        if amount + existing_value > max_amount:
            remaining = max_amount - existing_value
            if remaining <= 0:
                return RiskCheckResult(False, f"单票仓位已达上限{self.limits.max_position_pct*100:.0f}%")
            return RiskCheckResult(
                True,
                f"仓位调整至{remaining:.0f}元(上限{self.limits.max_position_pct*100:.0f}%)",
                adjusted_amount=remaining,
            )

        # 6. Total position limit
        total_invested = sum(
            p.get("qty", 0) * p.get("price", p.get("cost", 0))
            for p in positions
        )
        if (total_invested + amount) / max(total_assets, 1) > self.limits.max_total_position_pct:
            return RiskCheckResult(
                False,
                f"总仓位将超过{self.limits.max_total_position_pct*100:.0f}%",
            )

        # 7. Sufficient cash
        if amount > cash:
            adjusted = cash * 0.95  # Leave 5% buffer
            if adjusted <= 0:
                return RiskCheckResult(False, "可用资金不足")
            return RiskCheckResult(True, f"资金调整至{adjusted:.0f}元", adjusted_amount=adjusted)

        # 8. Max drawdown check
        initial = account.get("initial_cash", total_assets)
        if initial > 0:
            drawdown_pct = ((total_assets / initial) - 1) * 100
            if drawdown_pct <= self.limits.max_drawdown_pct:
                return RiskCheckResult(
                    False,
                    f"组合回撤{drawdown_pct:.1f}%已触发风控线({self.limits.max_drawdown_pct}%)",
                )

        return RiskCheckResult(True, "通过", adjusted_amount=amount)

    def check_sell(self, code: str, account: dict) -> dict:
        """Check if a position should be force-sold (stop-loss/take-profit).

        Returns: {should_sell, reason, pnl_pct}
        """
        positions = account.get("positions", [])
        for p in positions:
            if p.get("code") != code:
                continue
            cost = p.get("cost", 0)
            price = p.get("price", 0)
            if not cost or not price:
                continue
            pnl_pct = ((price / cost) - 1) * 100
            if pnl_pct <= self.limits.stop_loss_pct:
                return {
                    "should_sell": True,
                    "reason": f"触发止损({pnl_pct:.1f}% <= {self.limits.stop_loss_pct}%)",
                    "pnl_pct": round(pnl_pct, 2),
                }
            if pnl_pct >= self.limits.take_profit_pct:
                return {
                    "should_sell": True,
                    "reason": f"触发止盈({pnl_pct:.1f}% >= {self.limits.take_profit_pct}%)",
                    "pnl_pct": round(pnl_pct, 2),
                }
        return {"should_sell": False, "reason": "", "pnl_pct": 0.0}

    def check_stop_loss(self, code: str, current_price: float, avg_cost: float) -> bool:
        """Check if a position should be stopped out (simple boolean check)."""
        if avg_cost <= 0:
            return False
        loss_pct = (avg_cost - current_price) / avg_cost * 100
        if loss_pct >= abs(self.limits.stop_loss_pct):
            logger.warning("risk.stop_loss", code=code, loss_pct=f"{loss_pct:.1f}%")
            return True
        return False

    # ---- Post-trade tracking ----

    def record_trade(self) -> None:
        """Record a completed trade (call after order fills)."""
        self._reset_daily()
        self._daily_trades += 1

    def update_peak(self, total_value: float) -> None:
        """Track peak account value for drawdown calculation."""
        if total_value > self._peak_value:
            self._peak_value = total_value

    def get_drawdown(self, current_value: float) -> float:
        """Calculate current drawdown from peak."""
        if self._peak_value <= 0:
            return 0.0
        return (self._peak_value - current_value) / self._peak_value * 100

    def is_halted(self, current_value: float) -> bool:
        """Check if trading should be halted due to max drawdown."""
        dd = self.get_drawdown(current_value)
        if dd >= abs(self.limits.max_drawdown_pct):
            logger.error("risk.halt", drawdown=f"{dd:.1f}%")
            return True
        return False

    # ---- Status ----

    def get_status(self) -> dict:
        """Get current risk manager status for display."""
        self._reset_daily()
        return {
            "daily_trades": self._daily_trades,
            "max_daily_trades": self.limits.max_daily_trades,
            "max_position_pct": self.limits.max_position_pct,
            "max_total_position_pct": self.limits.max_total_position_pct,
            "max_total_positions": self.limits.max_total_positions,
            "max_single_order_amount": self.limits.max_single_order_amount,
            "stop_loss_pct": self.limits.stop_loss_pct,
            "take_profit_pct": self.limits.take_profit_pct,
            "max_drawdown_pct": self.limits.max_drawdown_pct,
            "chase_high_pct": self.limits.chase_high_pct,
            "peak_value": round(self._peak_value, 2),
        }


# ---- Global singleton ----

_risk_manager = RiskManager()


def get_risk_manager() -> RiskManager:
    """Get the global risk manager instance."""
    return _risk_manager


def configure_risk(limits: RiskLimits) -> None:
    """Reconfigure the global risk manager with new limits."""
    global _risk_manager
    _risk_manager = RiskManager(limits)
