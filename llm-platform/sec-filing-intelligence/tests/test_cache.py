"""Cache semantics, including the ones that silently cost money when wrong."""

from __future__ import annotations

import asyncio

from filing_intel.cache import InMemoryCache, RedisCache, cache_key
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
