"""Cache backends.

Two implementations behind one interface. `InMemoryCache` is not a test double --
it is the real fallback when no Redis URL is configured, and it honours TTLs so
behaviour does not silently diverge between a laptop and a deployment.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import time
from typing import Any, Protocol


class CacheBackend(Protocol):
    async def get(self, key: str) -> str | None: ...
    async def set(self, key: str, value: str, ttl_seconds: int) -> None: ...
    async def delete(self, key: str) -> None: ...
    async def ping(self) -> bool: ...


def cache_key(namespace: str, payload: Any) -> str:
    """Stable key from arbitrary JSON-able arguments.

    `sort_keys=True` matters: without it, two logically identical tool calls
    produce different digests depending on dict insertion order and the cache
    silently never hits.
    """
    blob = json.dumps(payload, sort_keys=True, default=str, separators=(",", ":"))
    digest = hashlib.sha256(blob.encode()).hexdigest()[:32]
    return f"filing_intel:{namespace}:{digest}"


class InMemoryCache:
    """Process-local cache with real TTL expiry."""

    def __init__(self) -> None:
        self._data: dict[str, tuple[str, float]] = {}
        self._lock = asyncio.Lock()

    async def get(self, key: str) -> str | None:
        async with self._lock:
            entry = self._data.get(key)
            if entry is None:
                return None
            value, expires_at = entry
            if expires_at <= time.monotonic():
                del self._data[key]
                return None
            return value

    async def set(self, key: str, value: str, ttl_seconds: int) -> None:
        async with self._lock:
            self._data[key] = (value, time.monotonic() + ttl_seconds)

    async def delete(self, key: str) -> None:
        async with self._lock:
            self._data.pop(key, None)

    async def ping(self) -> bool:
        return True


class RedisCache:
    """Redis-backed cache. Falls back rather than failing the request.

    A cache is an optimisation; a Redis blip should degrade latency, not return
    a 500. Read and write failures are swallowed and reported through `healthy`.
    """

    def __init__(self, redis: Any) -> None:
        self._redis = redis
        self.healthy = True

    async def get(self, key: str) -> str | None:
        try:
            value = await self._redis.get(key)
            self.healthy = True
        except Exception:
            self.healthy = False
            return None
        if value is None:
            return None
        return value.decode() if isinstance(value, bytes) else str(value)

    async def set(self, key: str, value: str, ttl_seconds: int) -> None:
        try:
            await self._redis.set(key, value, ex=ttl_seconds)
            self.healthy = True
        except Exception:
            self.healthy = False

    async def delete(self, key: str) -> None:
        try:
            await self._redis.delete(key)
        except Exception:
            self.healthy = False

    async def ping(self) -> bool:
        try:
            await self._redis.ping()
            self.healthy = True
        except Exception:
            self.healthy = False
        return self.healthy


def build_cache(redis_url: str | None) -> CacheBackend:
    """Return a Redis cache when a URL is configured, else the in-process one."""
    if not redis_url:
        return InMemoryCache()
    try:
        from redis.asyncio import Redis
    except ImportError:  # pragma: no cover - redis is a declared dependency
        return InMemoryCache()
    return RedisCache(Redis.from_url(redis_url))
