"""QMT (迅投MiniQMT) broker implementation for live trading."""
from __future__ import annotations

import asyncio
from typing import Any

from backend.app.core.logging import get_logger
from backend.app.trading.brokers.base import AccountState, BaseBroker, Position
from backend.app.trading.events import OrderEvent, OrderStatus, OrderType, Side

logger = get_logger("broker.qmt")


class QMTBroker(BaseBroker):
    """QMT live trading broker via xtquant SDK.

    Requires:
      - MiniQMT client running locally
      - pip install xtquant (or bundled with QMT installation)
      - Account unlocked in QMT terminal

    Usage:
        broker = QMTBroker(account_id="your_account", path=r"D:/QMT/userdata_mini")
        await broker.connect()
    """

    def __init__(
        self,
        account_id: str = "",
        path: str = r"D:/国金MiniQMT/userdata_mini",
        session_id: int = 123456,
    ):
        self._account_id = account_id
        self._path = path
        self._session_id = session_id
        self._connected = False
        self._xt_trader: Any = None
        self._account_obj: Any = None
        self._lock = asyncio.Lock()

    async def connect(self) -> bool:
        """Connect to QMT via xtquant."""
        try:
            from xtquant.xttrader import XtQuantTrader
            from xtquant.xttype import StockAccount

            self._xt_trader = XtQuantTrader(self._path, self._session_id)
            self._xt_trader.start()
            connect_result = self._xt_trader.connect()
            if connect_result != 0:
                logger.error("qmt.connect_failed", code=connect_result)
                return False

            self._account_obj = StockAccount(self._account_id)
            subscribe_result = self._xt_trader.subscribe(self._account_obj)
            if subscribe_result != 0:
                logger.warning("qmt.subscribe_failed", code=subscribe_result)

            self._connected = True
            logger.info("qmt.connected", account=self._account_id)
            return True
        except ImportError:
            logger.error("qmt.xtquant_not_found", msg="pip install xtquant or add QMT path to sys.path")
            return False
        except Exception as e:
            logger.error("qmt.connect_error", error=str(e))
            return False

    async def disconnect(self) -> None:
        if self._xt_trader:
            self._xt_trader.stop()
            self._connected = False
            logger.info("qmt.disconnected")

    @property
    def connected(self) -> bool:
        return self._connected

    def _to_xt_code(self, code: str) -> str:
        """Convert internal code (sh600519) to QMT format (600519.SH)."""
        if code.startswith("sh"):
            return code[2:] + ".SH"
        elif code.startswith("sz"):
            return code[2:] + ".SZ"
        return code

    def _from_xt_code(self, xt_code: str) -> str:
        """Convert QMT format (600519.SH) to internal (sh600519)."""
        parts = xt_code.split(".")
        if len(parts) == 2:
            return parts[1].lower() + parts[0]
        return xt_code

    async def submit_order(self, order: OrderEvent) -> OrderEvent:
        if not self._connected:
            order.status = OrderStatus.REJECTED
            return order

        from xtquant.xtconstant import (
            FIX_PRICE,  # 限价
            LATEST_PRICE,  # 市价(最新价)
            STOCK_BUY,
            STOCK_SELL,
        )

        xt_code = self._to_xt_code(order.code)
        direction = STOCK_BUY if order.side == Side.BUY else STOCK_SELL
        price_type = FIX_PRICE if order.order_type == OrderType.LIMIT else LATEST_PRICE
        price = order.price if order.order_type == OrderType.LIMIT else 0

        async with self._lock:
            try:
                order_id = self._xt_trader.order_stock(
                    self._account_obj,
                    xt_code,
                    direction,
                    int(order.qty),
                    price_type,
                    price,
                )
                if order_id and order_id > 0:
                    order.order_id = str(order_id)
                    order.status = OrderStatus.SUBMITTED
                    logger.info("qmt.order_submitted", id=order_id, code=order.code,
                                side=order.side.value, qty=order.qty)
                else:
                    order.status = OrderStatus.REJECTED
                    logger.warning("qmt.order_rejected", code=order.code)
            except Exception as e:
                order.status = OrderStatus.REJECTED
                logger.error("qmt.order_error", error=str(e))

        return order

    async def cancel_order(self, order_id: str) -> bool:
        if not self._connected:
            return False
        try:
            result = self._xt_trader.cancel_order_stock(self._account_obj, int(order_id))
            return result == 0
        except Exception as e:
            logger.error("qmt.cancel_error", order_id=order_id, error=str(e))
            return False

    async def get_positions(self) -> dict[str, Position]:
        if not self._connected:
            return {}
        try:
            positions = self._xt_trader.query_stock_positions(self._account_obj)
            result = {}
            for p in positions:
                if p.volume > 0:
                    code = self._from_xt_code(p.stock_code)
                    result[code] = Position(
                        code=code,
                        qty=p.volume,
                        avg_cost=p.avg_price,
                        market_value=p.market_value,
                        unrealized_pnl=(p.market_value - p.avg_price * p.volume),
                    )
            return result
        except Exception as e:
            logger.error("qmt.positions_error", error=str(e))
            return {}

    async def get_account(self) -> AccountState:
        if not self._connected:
            return AccountState()
        try:
            asset = self._xt_trader.query_stock_asset(self._account_obj)
            positions = await self.get_positions()
            return AccountState(
                cash=asset.cash if asset else 0,
                positions=positions,
                total_value=asset.total_asset if asset else 0,
                frozen=asset.frozen_cash if asset else 0,
            )
        except Exception as e:
            logger.error("qmt.account_error", error=str(e))
            return AccountState()

    async def get_latest_price(self, code: str) -> float:
        """Get latest price via xtquant data interface."""
        try:
            from xtquant import xtdata
            xt_code = self._to_xt_code(code)
            tick = xtdata.get_full_tick([xt_code])
            if xt_code in tick:
                return tick[xt_code]["lastPrice"]
        except Exception:
            pass
        return 0.0
