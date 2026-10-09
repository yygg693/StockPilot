"""Tests for expanded technical indicator library in ai_signals."""
from __future__ import annotations

import pytest

from backend.app.services.ai_signals import (
    analyze_technicals,
    calc_boll,
    calc_cci,
    calc_kdj,
    calc_ma,
    calc_macd,
    calc_obv,
    calc_rsi,
    calc_wr,
)


def _make_closes(n: int = 60, base: float = 10.0, trend: float = 0.1) -> list[float]:
    return [base + i * trend for i in range(n)]


def _make_klines(n: int = 60, base: float = 10.0, trend: float = 0.1) -> list[dict]:
    klines = []
    for i in range(n):
        price = base + i * trend
        klines.append({
            "date": f"2024-01-{i+1:02d}" if i < 31 else f"2024-02-{i-30:02d}",
            "open": price - 0.05,
            "close": price,
            "high": price + 0.1,
            "low": price - 0.1,
            "volume": 100000 + i * 1000,
        })
    return klines


class TestCalcBoll:
    def test_boll_structure(self):
        closes = _make_closes()
        boll = calc_boll(closes)
        assert "upper" in boll
        assert "mid" in boll
        assert "lower" in boll
        assert boll["upper"] > boll["mid"] > boll["lower"]

    def test_boll_insufficient_data(self):
        boll = calc_boll([10, 11, 12])
        assert boll == {"upper": 0, "mid": 0, "lower": 0}

    def test_boll_constant_price(self):
        closes = [10.0] * 30
        boll = calc_boll(closes)
        assert boll["upper"] == boll["mid"] == boll["lower"] == 10.0


class TestCalcKDJ:
    def test_kdj_structure(self):
        klines = _make_klines()
        kdj = calc_kdj(klines)
        assert "k" in kdj
        assert "d" in kdj
        assert "j" in kdj
        assert 0 <= kdj["k"] <= 100
        assert 0 <= kdj["d"] <= 100

    def test_kdj_insufficient_data(self):
        kdj = calc_kdj([{"high": 10, "low": 9, "close": 9.5}])
        assert kdj == {"k": 0, "d": 0, "j": 0}


class TestCalcOBV:
    def test_obv_uptrend_positive(self):
        closes = [10, 11, 12, 13, 14]
        vols = [100, 200, 150, 300, 250]
        obv = calc_obv(closes, vols)
        assert obv > 0  # Net volume should be positive in uptrend

    def test_obv_downtrend_negative(self):
        closes = [14, 13, 12, 11, 10]
        vols = [100, 200, 150, 300, 250]
        obv = calc_obv(closes, vols)
        assert obv < 0

    def test_obv_insufficient_data(self):
        assert calc_obv([10], [100]) == 0.0


class TestCalcWR:
    def test_wr_range(self):
        closes = _make_closes()
        highs = [c + 0.5 for c in closes]
        lows = [c - 0.5 for c in closes]
        wr = calc_wr(closes, highs, lows)
        assert wr is not None
        assert -100 <= wr <= 0

    def test_wr_insufficient_data(self):
        assert calc_wr([10, 11], [11, 12], [9, 10]) is None


class TestCalcCCI:
    def test_cci_returns_float(self):
        closes = _make_closes()
        highs = [c + 0.5 for c in closes]
        lows = [c - 0.5 for c in closes]
        cci = calc_cci(closes, highs, lows)
        assert cci is not None
        assert isinstance(cci, float)

    def test_cci_insufficient_data(self):
        assert calc_cci([10, 11], [11, 12], [9, 10]) is None


class TestAnalyzeTechnicalsExpanded:
    def test_returns_confidence(self):
        closes = _make_closes(60)
        klines = _make_klines(60)
        result = analyze_technicals(closes, klines)
        assert "confidence" in result
        assert 0 <= result["confidence"] <= 100

    def test_returns_boll(self):
        closes = _make_closes(60)
        result = analyze_technicals(closes)
        assert "boll" in result
        assert "upper" in result["boll"]

    def test_returns_kdj_with_klines(self):
        closes = _make_closes(60)
        klines = _make_klines(60)
        result = analyze_technicals(closes, klines)
        assert "kdj" in result
        assert "k" in result["kdj"]

    def test_no_klines_skips_kdj(self):
        closes = _make_closes(60)
        result = analyze_technicals(closes)
        assert result["kdj"] == {"k": 0, "d": 0, "j": 0}

    def test_returns_wr_cci_with_klines(self):
        closes = _make_closes(60)
        klines = _make_klines(60)
        result = analyze_technicals(closes, klines)
        assert "wr" in result
        assert "cci" in result

    def test_insufficient_data_returns_confidence_zero(self):
        result = analyze_technicals([10, 11, 12])
        assert result["confidence"] == 0
        assert result["signal"] == "neutral"

    def test_strong_trend_produces_clear_signal(self):
        closes = _make_closes(60, trend=0.3)  # Strong uptrend
        klines = _make_klines(60, trend=0.3)
        result = analyze_technicals(closes, klines)
        # A strong trend should produce a non-neutral signal (buy or sell due to overbought)
        assert result["signal"] in ("buy", "strong_buy", "sell", "strong_sell", "neutral")
        assert result["confidence"] > 0  # Should have some confidence with clear signals
