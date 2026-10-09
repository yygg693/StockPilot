"""Tests for backend.app.core.risk — unified risk management engine."""
from __future__ import annotations

import pytest

from backend.app.core.risk import (
    RiskCheckResult,
    RiskLimits,
    RiskManager,
    configure_risk,
    get_risk_manager,
)


@pytest.fixture
def rm():
    """Fresh RiskManager for each test."""
    return RiskManager()


@pytest.fixture
def basic_account():
    """Basic account dict for testing."""
    return {
        "cash": 500_000,
        "total_assets": 1_000_000,
        "initial_cash": 1_000_000,
        "positions": [],
    }


class TestCheckBuy:
    def test_normal_buy_allowed(self, rm, basic_account):
        result = rm.check_buy("sh600519", 50_000, basic_account)
        assert result.allowed is True

    def test_exceeds_single_order_limit(self, rm, basic_account):
        result = rm.check_buy("sh600519", 300_000, basic_account)
        assert result.allowed is False
        assert "限额" in result.reason

    def test_chase_high_blocked(self, rm, basic_account):
        result = rm.check_buy("sh600519", 50_000, basic_account, change_pct=15.0)
        assert result.allowed is False
        assert "追高" in result.reason

    def test_position_concentration_adjusted(self, rm):
        # Use total_assets=500k so 20% limit = 100k, but amount=150k < single_order_limit=200k
        account = {
            "cash": 500_000,
            "total_assets": 500_000,
            "initial_cash": 500_000,
            "positions": [],
        }
        result = rm.check_buy("sh600519", 150_000, account)
        assert result.allowed is True
        assert result.adjusted_amount < 150_000
        assert result.adjusted_amount == pytest.approx(100_000, rel=0.01)

    def test_insufficient_cash_adjusted(self, rm, basic_account):
        account = {**basic_account, "cash": 30_000, "total_assets": 30_000}
        result = rm.check_buy("sh600519", 50_000, account)
        assert result.allowed is True
        assert result.adjusted_amount < 50_000

    def test_max_positions_reached(self, rm, basic_account):
        positions = [{"code": f"sh60050{i}", "qty": 100, "price": 100} for i in range(10)]
        account = {**basic_account, "positions": positions}
        result = rm.check_buy("sh600519", 10_000, account)
        assert result.allowed is False
        assert "上限" in result.reason

    def test_daily_trade_limit(self, rm, basic_account):
        for _ in range(10):
            rm.record_trade()
        result = rm.check_buy("sh600519", 10_000, basic_account)
        assert result.allowed is False
        assert "次数" in result.reason

    def test_max_drawdown_blocks(self, rm, basic_account):
        account = {
            "cash": 800_000,
            "total_assets": 800_000,
            "initial_cash": 1_000_000,
            "positions": [],
        }
        result = rm.check_buy("sh600519", 10_000, account)
        assert result.allowed is False
        assert "回撤" in result.reason


class TestCheckSell:
    def test_stop_loss_triggered(self, rm):
        account = {
            "positions": [
                {"code": "sh600519", "cost": 100, "price": 90},  # -10% loss
            ]
        }
        result = rm.check_sell("sh600519", account)
        assert result["should_sell"] is True
        assert "止损" in result["reason"]

    def test_take_profit_triggered(self, rm):
        account = {
            "positions": [
                {"code": "sh600519", "cost": 100, "price": 125},  # +25% profit
            ]
        }
        result = rm.check_sell("sh600519", account)
        assert result["should_sell"] is True
        assert "止盈" in result["reason"]

    def test_no_action_in_range(self, rm):
        account = {
            "positions": [
                {"code": "sh600519", "cost": 100, "price": 105},  # +5%
            ]
        }
        result = rm.check_sell("sh600519", account)
        assert result["should_sell"] is False

    def test_position_not_found(self, rm):
        result = rm.check_sell("sh999999", {"positions": []})
        assert result["should_sell"] is False


class TestCheckStopLoss:
    def test_stop_loss_triggered(self, rm):
        assert rm.check_stop_loss("sh600519", 90, 100) is True

    def test_no_stop_loss(self, rm):
        assert rm.check_stop_loss("sh600519", 95, 100) is False

    def test_zero_cost(self, rm):
        assert rm.check_stop_loss("sh600519", 90, 0) is False


class TestDrawdownTracking:
    def test_update_peak(self, rm):
        rm.update_peak(1_000_000)
        rm.update_peak(1_100_000)
        assert rm._peak_value == 1_100_000

    def test_get_drawdown(self, rm):
        rm.update_peak(1_000_000)
        dd = rm.get_drawdown(850_000)
        assert dd == pytest.approx(15.0, abs=0.1)

    def test_is_halted(self, rm):
        rm.update_peak(1_000_000)
        assert rm.is_halted(840_000) is True  # 16% drawdown > 15% limit
        assert rm.is_halted(900_000) is False  # 10% drawdown < 15% limit


class TestStatus:
    def test_get_status(self, rm):
        status = rm.get_status()
        assert "daily_trades" in status
        assert "max_daily_trades" in status
        assert "stop_loss_pct" in status
        assert status["max_daily_trades"] == 10

    def test_global_singleton(self):
        rm1 = get_risk_manager()
        rm2 = get_risk_manager()
        assert rm1 is rm2

    def test_configure_risk(self):
        custom = RiskLimits(max_daily_trades=5)
        configure_risk(custom)
        rm = get_risk_manager()
        assert rm.limits.max_daily_trades == 5
        # Reset to default
        configure_risk(RiskLimits())
