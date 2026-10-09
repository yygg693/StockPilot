"""Broker abstraction layer."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

from backend.app.trading.events import OrderEvent


@dataclass
class Position:
    code: str
    qty: float
    avg_cost: float
    market_value: float = 0.0
    unrealized_pnl: float = 0.0


@dataclass
class AccountState:
    cash: float = 1_000_000.0
    positions: dict[str, Position] = None  # type: ignore
    total_value: float = 1_000_000.0
    frozen: float = 0.0

    def __post_init__(self):
        if self.positions is None:
            self.positions = {}


class BaseBroker(ABC):
    """Abstract broker interface."""

    @abstractmethod
    async def submit_order(self, order: OrderEvent) -> OrderEvent:
        """Submit order to broker. Returns updated order with status."""
        ...

    @abstractmethod
    async def cancel_order(self, order_id: str) -> bool:
        ...

    @abstractmethod
    async def get_positions(self) -> dict[str, Position]:
        ...

    @abstractmethod
    async def get_account(self) -> AccountState:
        ...

    @abstractmethod
    async def get_latest_price(self, code: str) -> float:
        ...
