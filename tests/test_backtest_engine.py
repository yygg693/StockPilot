"""Tests for backend.app.services.backtest_engine — trading costs and metrics."""
from __future__ import annotations

import pytest

from backend.app.services.backtest_engine import (
    BacktestResult,
    TradeCost,
    TradeRecord,
    calc_buy_cost,
    calc_metrics,
    calc_sell_proceeds,
    run_backtest,
    DEFAULT_COMMISSION_RATE,
    DEFAULT_STAMP_DUTY_RATE,
    DEFAULT_SLIPPAGE,
    MIN_COMMISSION,
)


class TestCalcBuyCost:
    def test_basic_buy_cost(self):
        config = TradeCost()
        fill_price, total_cost = calc_buy_cost(10.0, 1000, config)
        # Fill price includes slippage
        assert fill_price == pytest.approx(10.0 * (1 + DEFAULT_SLIPPAGE))
        # Total cost = amount + commission + transfer
        amount = fill_price * 1000
        commission = max(amount * DEFAULT_COMMISSION_RATE, MIN_COMMISSION)
        transfer = amount * config.transfer_fee_rate
        assert total_cost == pytest.approx(amount + commission + transfer)

    def test_min_commission_applied(self):
        config = TradeCost()
        # Very small order — commission should be min 5 yuan
        fill_price, total_cost = calc_buy_cost(1.0, 100, config)
        amount = fill_price * 100
        assert amount * DEFAULT_COMMISSION_RATE < MIN_COMMISSION  # Would be < 5
        # So min commission kicks in
        assert total_cost > amount + MIN_COMMISSION - 0.01

    def test_zero_slippage(self):
        config = TradeCost(slippage=0.0)
        fill_price, _ = calc_buy_cost(20.0, 500, config)
        assert fill_price == pytest.approx(20.0)


class TestCalcSellProceeds:
    def test_basic_sell_proceeds(self):
        config = TradeCost()
        fill_price, net_proceeds = calc_sell_proceeds(10.0, 1000, config)
        # Fill price reduced by slippage
        assert fill_price == pytest.approx(10.0 * (1 - DEFAULT_SLIPPAGE))
        # Net = amount - commission - stamp_duty - transfer
        amount = fill_price * 1000
        commission = max(amount * DEFAULT_COMMISSION_RATE, MIN_COMMISSION)
        stamp_duty = amount * DEFAULT_STAMP_DUTY_RATE
        transfer = amount * config.transfer_fee_rate
        assert net_proceeds == pytest.approx(amount - commission - stamp_duty - transfer)

    def test_sell_has_stamp_duty_buy_does_not(self):
        config = TradeCost(slippage=0.0)
        _, buy_cost = calc_buy_cost(10.0, 1000, config)
        _, sell_proceeds = calc_sell_proceeds(10.0, 1000, config)
        amount = 10.0 * 1000
        # Buy: amount + commission + transfer
        # Sell: amount - commission - stamp_duty - transfer
        # Difference should include stamp_duty + 2*commission + 2*transfer
        spread = buy_cost - sell_proceeds
        expected_spread = (
            2 * max(amount * DEFAULT_COMMISSION_RATE, MIN_COMMISSION)
            + amount * DEFAULT_STAMP_DUTY_RATE
            + 2 * amount * config.transfer_fee_rate
        )
        assert spread == pytest.approx(expected_spread, rel=0.001)


class TestCalcMetrics:
    def test_empty_returns_zeros(self):
        result = calc_metrics([], [], 1_000_000)
        assert result["total_return"] == 0.0
        assert result["sharpe_ratio"] == 0.0
        assert result["total_trades"] == 0

    def test_profitable_trades(self):
        trades = [
            TradeRecord("2024-01-01", "2024-01-10", 10.0, 11.0, 1000,
                        net_pnl=1000, pnl_pct=10.0, total_cost=50, hold_days=9),
            TradeRecord("2024-02-01", "2024-02-05", 20.0, 21.0, 500,
                        net_pnl=500, pnl_pct=5.0, total_cost=60, hold_days=4),
        ]
        equity = [1_000_000, 1_001_000, 1_001_500]
        result = calc_metrics(trades, equity, 1_000_000)
        assert result["total_return"] > 0
        assert result["win_rate"] == 100.0
        assert result["total_trades"] == 2

    def test_mixed_win_loss(self):
        trades = [
            TradeRecord("2024-01-01", "2024-01-10", 10.0, 11.0, 1000,
                        net_pnl=1000, pnl_pct=10.0, total_cost=50, hold_days=9),
            TradeRecord("2024-02-01", "2024-02-05", 20.0, 19.0, 500,
                        net_pnl=-500, pnl_pct=-5.0, total_cost=60, hold_days=4),
        ]
        equity = [1_000_000, 1_001_000, 1_000_500]
        result = calc_metrics(trades, equity, 1_000_000)
        assert result["win_rate"] == 50.0
        assert result["avg_win"] > 0
        assert result["avg_loss"] < 0


class TestRunBacktest:
    def _make_klines(self, n: int = 60, base_price: float = 10.0) -> list[dict]:
        """Generate synthetic K-line data with an uptrend."""
        klines = []
        for i in range(n):
            price = base_price + i * 0.1  # Linear uptrend
            klines.append({
                "date": f"2024-01-{i+1:02d}" if i < 31 else f"2024-02-{i-30:02d}",
                "open": price - 0.05,
                "close": price,
                "high": price + 0.1,
                "low": price - 0.1,
                "volume": 100000,
            })
        return klines

    def test_insufficient_data(self):
        result = run_backtest([], strategy="ma_cross")
        assert "error" in result.summary

    def test_valid_backtest_returns_result(self):
        klines = self._make_klines(60)
        result = run_backtest(klines, strategy="ma_cross")
        assert isinstance(result, BacktestResult)
        assert "total_return" in result.summary
        assert isinstance(result.trades, list)
        assert isinstance(result.equity_curve, list)

    def test_bollinger_strategy(self):
        klines = self._make_klines(60)
        result = run_backtest(klines, strategy="bollinger")
        assert isinstance(result, BacktestResult)
        assert "total_return" in result.summary

    def test_momentum_strategy(self):
        klines = self._make_klines(60)
        result = run_backtest(klines, strategy="momentum")
        assert isinstance(result, BacktestResult)
        assert "total_return" in result.summary

    def test_custom_cost_config(self):
        klines = self._make_klines(60)
        custom = TradeCost(commission_rate=0.001, slippage=0.002)
        result = run_backtest(klines, strategy="ma_cross", cost_config=custom)
        assert isinstance(result, BacktestResult)
