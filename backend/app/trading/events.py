"""Event definitions for the trading engine."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class EventType(Enum):
    TICK = "TICK"
    BAR = "BAR"
    SIGNAL = "SIGNAL"
    ORDER = "ORDER"
    FILL = "FILL"
    POSITION = "POSITION"
    RISK = "RISK"
    TIMER = "TIMER"


class Side(Enum):
    BUY = "BUY"
    SELL = "SELL"


class OrderType(Enum):
    MARKET = "MARKET"
    LIMIT = "LIMIT"


class OrderStatus(Enum):
    PENDING = "PENDING"
    SUBMITTED = "SUBMITTED"
    FILLED = "FILLED"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    CANCELLED = "CANCELLED"
    REJECTED = "REJECTED"


@dataclass
class Event:
    type: EventType
    timestamp: datetime = field(default_factory=datetime.now)
    data: dict[str, Any] = field(default_factory=dict)


@dataclass
class TickEvent(Event):
    type: EventType = EventType.TICK
    code: str = ""
    price: float = 0.0
    volume: float = 0.0
    bid: float = 0.0
    ask: float = 0.0


@dataclass
class SignalEvent(Event):
    type: EventType = EventType.SIGNAL
    code: str = ""
    side: Side = Side.BUY
    strength: float = 1.0
    strategy: str = ""
    reason: str = ""


@dataclass
class OrderEvent(Event):
    type: EventType = EventType.ORDER
    order_id: str = ""
    code: str = ""
    side: Side = Side.BUY
    order_type: OrderType = OrderType.MARKET
    qty: float = 0.0
    price: float = 0.0
    status: OrderStatus = OrderStatus.PENDING
    strategy: str = ""


@dataclass
class FillEvent(Event):
    type: EventType = EventType.FILL
    order_id: str = ""
    code: str = ""
    side: Side = Side.BUY
    qty: float = 0.0
    price: float = 0.0
    commission: float = 0.0
    slippage: float = 0.0
