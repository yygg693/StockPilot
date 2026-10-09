"""Event-driven trading engine.

NOTE: This module is reserved for future live trading integration.
It is not currently wired into the FastAPI application. The event bus
and engine loop will be activated when real broker connectivity is added.
"""
from __future__ import annotations

import asyncio
import contextlib
from collections import defaultdict
from collections.abc import Callable, Coroutine
from typing import Any

from backend.app.core.logging import get_logger
from backend.app.trading.events import Event, EventType

logger = get_logger("trading.engine")

Handler = Callable[[Event], Coroutine[Any, Any, None]]


class EventBus:
    """Async pub/sub event bus."""

    def __init__(self):
        self._handlers: dict[EventType, list[Handler]] = defaultdict(list)
        self._queue: asyncio.Queue[Event] = asyncio.Queue()

    def subscribe(self, event_type: EventType, handler: Handler) -> None:
        self._handlers[event_type].append(handler)

    def unsubscribe(self, event_type: EventType, handler: Handler) -> None:
        handlers = self._handlers.get(event_type, [])
        if handler in handlers:
            handlers.remove(handler)

    async def publish(self, event: Event) -> None:
        await self._queue.put(event)

    def publish_sync(self, event: Event) -> None:
        self._queue.put_nowait(event)

    async def process_one(self) -> bool:
        """Process a single event from the queue. Returns False if empty."""
        try:
            event = self._queue.get_nowait()
        except asyncio.QueueEmpty:
            return False
        handlers = self._handlers.get(event.type, [])
        for handler in handlers:
            try:
                await handler(event)
            except Exception as e:
                logger.error("event.handler_error", type=event.type.value, error=str(e))
        return True

    async def drain(self) -> int:
        """Process all pending events. Returns count processed."""
        count = 0
        while await self.process_one():
            count += 1
        return count


class TradingEngine:
    """Main trading engine loop."""

    def __init__(self, bus: EventBus):
        self.bus = bus
        self._running = False
        self._task: asyncio.Task | None = None
        self._tick_interval = 3.0  # seconds between market data polls

    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._loop())
        logger.info("engine.started")

    async def stop(self) -> None:
        self._running = False
        if self._task:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
        logger.info("engine.stopped")

    async def _loop(self) -> None:
        while self._running:
            # Drain event queue
            await self.bus.drain()
            # Sleep until next tick
            await asyncio.sleep(self._tick_interval)

    @property
    def is_running(self) -> bool:
        return self._running
