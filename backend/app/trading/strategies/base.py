"""Strategy framework: base class + example MA cross strategy."""
from __future__ import annotations

from abc import ABC, abstractmethod
from collections import deque

from backend.app.trading.events import Side, SignalEvent, TickEvent


class BaseStrategy(ABC):
    """Abstract strategy that consumes market data and emits signals."""

    name: str = "base"

    @abstractmethod
    def on_tick(self, tick: TickEvent) -> SignalEvent | None:
        """Process a tick and optionally emit a signal."""
        ...


class MACrossStrategy(BaseStrategy):
    """MA5/MA20 golden cross strategy."""

    name = "ma_cross"

    def __init__(self, fast: int = 5, slow: int = 20):
        self.fast = fast
        self.slow = slow
        self._prices: deque[float] = deque(maxlen=slow)
        self._prev_fast: float = 0.0
        self._prev_slow: float = 0.0
        self._in_position = False

    def on_tick(self, tick: TickEvent) -> SignalEvent | None:
        self._prices.append(tick.price)
        if len(self._prices) < self.slow:
            return None

        prices = list(self._prices)
        fast_ma = sum(prices[-self.fast:]) / self.fast
        slow_ma = sum(prices) / self.slow

        signal = None
        if self._prev_fast > 0 and self._prev_slow > 0:
            # Golden cross
            if self._prev_fast <= self._prev_slow and fast_ma > slow_ma and not self._in_position:
                signal = SignalEvent(
                    code=tick.code,
                    side=Side.BUY,
                    strength=1.0,
                    strategy=self.name,
                    reason=f"MA{self.fast}上穿MA{self.slow}",
                )
                self._in_position = True
            # Death cross
            elif self._prev_fast >= self._prev_slow and fast_ma < slow_ma and self._in_position:
                signal = SignalEvent(
                    code=tick.code,
                    side=Side.SELL,
                    strength=1.0,
                    strategy=self.name,
                    reason=f"MA{self.fast}下穿MA{self.slow}",
                )
                self._in_position = False

        self._prev_fast = fast_ma
        self._prev_slow = slow_ma
        return signal


class MomentumStrategy(BaseStrategy):
    """Simple momentum: buy when N-day return exceeds threshold."""

    name = "momentum"

    def __init__(self, lookback: int = 20, threshold_pct: float = 10.0):
        self.lookback = lookback
        self.threshold_pct = threshold_pct
        self._prices: deque[float] = deque(maxlen=lookback + 1)
        self._in_position = False

    def on_tick(self, tick: TickEvent) -> SignalEvent | None:
        self._prices.append(tick.price)
        if len(self._prices) < self.lookback + 1:
            return None

        prices = list(self._prices)
        ret = (prices[-1] - prices[0]) / prices[0] * 100

        if ret > self.threshold_pct and not self._in_position:
            self._in_position = True
            return SignalEvent(
                code=tick.code, side=Side.BUY, strength=min(ret / self.threshold_pct, 2.0),
                strategy=self.name, reason=f"{self.lookback}日涨幅{ret:.1f}%",
            )
        elif ret < 0 and self._in_position:
            self._in_position = False
            return SignalEvent(
                code=tick.code, side=Side.SELL, strength=1.0,
                strategy=self.name, reason=f"动量消失 ret={ret:.1f}%",
            )
        return None
