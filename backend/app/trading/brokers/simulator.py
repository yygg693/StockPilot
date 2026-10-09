"""Simulated broker for paper trading and backtesting."""
from __future__ import annotations

import uuid

from backend.app.core.logging import get_logger
from backend.app.trading.brokers.base import AccountState, BaseBroker, Position
from backend.app.trading.events import OrderEvent, OrderStatus, Side

logger = get_logger("broker.simulator")


class SimulatorBroker(BaseBroker):
    """Paper trading broker with configurable slippage and commission."""

    def __init__(
        self,
        initial_cash: float = 1_000_000.0,
        commission_rate: float = 0.0003,  # 万三
        slippage_pct: float = 0.001,     # 0.1%
        stamp_tax_rate: float = 0.001,   # 印花税(卖出)
    ):
        self._account = AccountState(cash=initial_cash)
        self._commission_rate = commission_rate
        self._slippage_pct = slippage_pct
        self._stamp_tax_rate = stamp_tax_rate
        self._prices: dict[str, float] = {}
        self._orders: dict[str, OrderEvent] = {}

    def set_price(self, code: str, price: float) -> None:
        """Feed latest price for simulation."""
        self._prices[code] = price

    async def submit_order(self, order: OrderEvent) -> OrderEvent:
        order.order_id = order.order_id or str(uuid.uuid4())[:8]
        price = self._prices.get(order.code, order.price)
        if price <= 0:
            order.status = OrderStatus.REJECTED
            return order

        # Apply slippage
        if order.side == Side.BUY:
            fill_price = price * (1 + self._slippage_pct)
        else:
            fill_price = price * (1 - self._slippage_pct)

        amount = fill_price * order.qty
        commission = max(amount * self._commission_rate, 5.0)  # 最低5元

        if order.side == Side.BUY:
            total_cost = amount + commission
            if total_cost > self._account.cash:
                order.status = OrderStatus.REJECTED
                logger.warning("sim.insufficient_cash", need=total_cost, have=self._account.cash)
                return order
            self._account.cash -= total_cost
            # Update position
            pos = self._account.positions.get(order.code)
            if pos:
                new_qty = pos.qty + order.qty
                pos.avg_cost = (pos.avg_cost * pos.qty + fill_price * order.qty) / new_qty
                pos.qty = new_qty
            else:
                self._account.positions[order.code] = Position(
                    code=order.code, qty=order.qty, avg_cost=fill_price
                )
        else:  # SELL
            pos = self._account.positions.get(order.code)
            if not pos or pos.qty < order.qty:
                order.status = OrderStatus.REJECTED
                return order
            stamp_tax = amount * self._stamp_tax_rate
            self._account.cash += amount - commission - stamp_tax
            pos.qty -= order.qty
            if pos.qty <= 0:
                del self._account.positions[order.code]

        order.status = OrderStatus.FILLED
        order.price = fill_price
        self._orders[order.order_id] = order
        logger.info("sim.fill", code=order.code, side=order.side.value, qty=order.qty, price=round(fill_price, 2))
        return order

    async def cancel_order(self, order_id: str) -> bool:
        order = self._orders.get(order_id)
        if order and order.status == OrderStatus.PENDING:
            order.status = OrderStatus.CANCELLED
            return True
        return False

    async def get_positions(self) -> dict[str, Position]:
        # Update market values
        for code, pos in self._account.positions.items():
            price = self._prices.get(code, pos.avg_cost)
            pos.market_value = price * pos.qty
            pos.unrealized_pnl = (price - pos.avg_cost) * pos.qty
        return self._account.positions

    async def get_account(self) -> AccountState:
        positions = await self.get_positions()
        self._account.total_value = self._account.cash + sum(
            p.market_value for p in positions.values()
        )
        return self._account

    async def get_latest_price(self, code: str) -> float:
        return self._prices.get(code, 0.0)
