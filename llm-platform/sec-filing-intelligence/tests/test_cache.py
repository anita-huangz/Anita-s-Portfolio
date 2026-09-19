"""Cache semantics, including the ones that silently cost money when wrong."""

from __future__ import annotations

import asyncio
from typing import Any

from filing_intel.cache import InMemoryCache, RedisCache, cache_key
from filing_intel.cache.store import build_cache
from filing_intel.contracts import TokenUsage


async def test_roundtrip():
    cache = InMemoryCache()
    await cache.set("k", "v", 60)
    assert await cache.get("k") == "v"


async def test_missing_key_is_none():
    assert await InMemoryCache().get("nope") is None


async def test_ttl_expiry_is_real():
    cache = InMemoryCache()
    await cache.set("k", "v", 0)
    await asyncio.sleep(0.01)
    assert await cache.get("k") is None


async def test_delete():
    cache = InMemoryCache()
    await cache.set("k", "v", 60)
    await cache.delete("k")
    assert await cache.get("k") is None


def test_cache_key_is_insensitive_to_dict_ordering():
    """Without sorted keys the cache never hits and nobody notices."""
    assert cache_key("t", {"a": 1, "b": 2}) == cache_key("t", {"b": 2, "a": 1})


def test_cache_key_changes_with_values_and_namespace():
    assert cache_key("t", {"a": 1}) != cache_key("t", {"a": 2})
    assert cache_key("t1", {"a": 1}) != cache_key("t2", {"a": 1})


class BrokenRedis:
    async def get(self, key):
        raise ConnectionError("redis down")

    async def set(self, key, value, ex=None):
        raise ConnectionError("redis down")

    async def delete(self, key):
        raise ConnectionError("redis down")

    async def ping(self):
        raise ConnectionError("redis down")


async def test_redis_failure_degrades_instead_of_raising():
    """A cache outage should cost latency, not return a 500."""
    cache = RedisCache(BrokenRedis())
    assert await cache.get("k") is None
    await cache.set("k", "v", 60)
    assert await cache.ping() is False
    assert cache.healthy is False


class FakeRedis:
    """Enough of the redis.asyncio surface to exercise the happy path."""

    def __init__(self, raw: bool = False) -> None:
        self.data: dict[str, Any] = {}
        self.ttls: dict[str, int] = {}
        self._raw = raw

    async def get(self, key):
        value = self.data.get(key)
        if value is None:
            return None
        # A real client returns bytes unless decode_responses is set, and the
        # deployment does not set it.
        return value.encode() if self._raw else value

    async def set(self, key, value, ex=None):
        self.data[key] = value
        self.ttls[key] = ex

    async def delete(self, key):
        self.data.pop(key, None)

    async def ping(self):
        return True


async def test_redis_roundtrip_carries_the_ttl_through():
    cache = RedisCache(FakeRedis())
    await cache.set("k", "v", 45)
    assert await cache.get("k") == "v"
    assert cache._redis.ttls["k"] == 45
    assert await cache.ping() is True
    assert cache.healthy is True


async def test_bytes_from_redis_are_decoded_to_the_str_the_caller_expects():
    cache = RedisCache(FakeRedis(raw=True))
    await cache.set("k", "v", 60)
    assert await cache.get("k") == "v"


async def test_a_redis_miss_is_none_not_an_error():
    assert await RedisCache(FakeRedis()).get("absent") is None


async def test_redis_delete_removes_the_key():
    cache = RedisCache(FakeRedis())
    await cache.set("k", "v", 60)
    await cache.delete("k")
    assert await cache.get("k") is None


async def test_a_failed_delete_marks_the_cache_unhealthy_without_raising():
    cache = RedisCache(BrokenRedis())
    await cache.delete("k")
    assert cache.healthy is False


async def test_recovery_after_an_outage_clears_the_unhealthy_flag():
    # `healthy` drives the readiness endpoint, so a flag that latches on would
    # keep reporting an outage that is over.
    cache = RedisCache(FakeRedis())
    cache.healthy = False
    await cache.get("k")
    assert cache.healthy is True


def test_no_redis_url_configured_means_the_in_process_cache():
    assert isinstance(build_cache(None), InMemoryCache)
    assert isinstance(build_cache(""), InMemoryCache)


def test_a_redis_url_builds_a_redis_backed_cache():
    assert isinstance(build_cache("redis://localhost:6379/0"), RedisCache)


# --------------------------------------------------------------------------- #
# Sessions
# --------------------------------------------------------------------------- #


async def test_session_created_then_retrieved(sessions):
    session = await sessions.get_or_create(None, ticker="AAPL")
    session.turns = 2
    session.usage = TokenUsage(input_tokens=10)
    await sessions.save(session)

    loaded = await sessions.get(session.session_id)
    assert loaded is not None
    assert loaded.turns == 2
    assert loaded.ticker == "AAPL"
    assert loaded.usage.input_tokens == 10


async def test_get_or_create_reuses_an_existing_session(sessions):
    first = await sessions.get_or_create(None, "AAPL")
    await sessions.save(first)
    second = await sessions.get_or_create(first.session_id)
    assert second.session_id == first.session_id


async def test_get_or_create_with_unknown_id_keeps_the_caller_id(sessions):
    session = await sessions.get_or_create("caller-supplied-id")
    assert session.session_id == "caller-supplied-id"


async def test_corrupt_session_is_discarded_not_raised(sessions, cache):
    await cache.set("filing_intel:session:bad", "{not json", 60)
    assert await sessions.get("bad") is None
    # And the poisoned entry is gone, so the next turn starts clean.
    assert await cache.get("filing_intel:session:bad") is None


async def test_session_delete(sessions):
    session = await sessions.get_or_create(None)
    await sessions.save(session)
    await sessions.delete(session.session_id)
    assert await sessions.get(session.session_id) is None
