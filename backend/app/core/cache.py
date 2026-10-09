"""Unified async-safe TTL cache with optional LRU eviction."""
from __future__ import annotations

import asyncio
import time
from collections import OrderedDict
from typing import Any


class TTLCache:
    """Thread/task-safe TTL cache with optional max-size LRU eviction.

    Usage:
        cache = TTLCache(default_ttl=30, max_size=512)
        cache.set("key", value, ttl=60)
        val = cache.get("key")  # None if expired/missing
    """

    def __init__(self, default_ttl: float = 30.0, max_size: int = 1024):
        self._default_ttl = default_ttl
        self._max_size = max_size
        self._store: OrderedDict[str, tuple[float, Any]] = OrderedDict()
        self._lock = asyncio.Lock()

    async def get(self, key: str) -> Any | None:
        async with self._lock:
            item = self._store.get(key)
            if item is None:
                return None
            expires, value = item
            if time.monotonic() > expires:
                del self._store[key]
                return None
            # LRU: move to end
            self._store.move_to_end(key)
            return value

    async def set(self, key: str, value: Any, ttl: float | None = None) -> None:
        ttl = ttl if ttl is not None else self._default_ttl
        expires = time.monotonic() + ttl
        async with self._lock:
            self._store[key] = (expires, value)
            self._store.move_to_end(key)
            while len(self._store) > self._max_size:
                self._store.popitem(last=False)

    async def delete(self, key: str) -> None:
        async with self._lock:
            self._store.pop(key, None)

    async def clear(self) -> None:
        async with self._lock:
            self._store.clear()

    def get_sync(self, key: str) -> Any | None:
        """Non-async get for sync contexts (no lock, best-effort)."""
        item = self._store.get(key)
        if item is None:
            return None
        expires, value = item
        if time.monotonic() > expires:
            self._store.pop(key, None)
            return None
        return value

    def set_sync(self, key: str, value: Any, ttl: float | None = None) -> None:
        ttl = ttl if ttl is not None else self._default_ttl
        self._store[key] = (time.monotonic() + ttl, value)
        self._store.move_to_end(key)
        while len(self._store) > self._max_size:
            self._store.popitem(last=False)


class SyncTTLCache:
    """Simple thread-safe TTL cache for sync code paths (legacy migration)."""

    def __init__(self, default_ttl: float = 30.0, max_size: int = 1024):
        import threading
        self._default_ttl = default_ttl
        self._max_size = max_size
        self._store: OrderedDict[str, tuple[float, Any]] = OrderedDict()
        self._lock = threading.Lock()

    def get(self, key: str) -> Any | None:
        with self._lock:
            item = self._store.get(key)
            if item is None:
                return None
            expires, value = item
            if time.monotonic() > expires:
                del self._store[key]
                return None
            self._store.move_to_end(key)
            return value

    def set(self, key: str, value: Any, ttl: float | None = None) -> None:
        ttl = ttl if ttl is not None else self._default_ttl
        with self._lock:
            self._store[key] = (time.monotonic() + ttl, value)
            self._store.move_to_end(key)
            while len(self._store) > self._max_size:
                self._store.popitem(last=False)

    def delete(self, key: str) -> None:
        with self._lock:
            self._store.pop(key, None)

    def clear(self) -> None:
        with self._lock:
            self._store.clear()
