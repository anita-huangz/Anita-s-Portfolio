"""The cache decorator: pluggable eviction, optional expiry.

`lru_cache` answers "has this been computed?" This answers the question a real
service asks, which is "has this been computed *recently enough*?" A memoized
exchange rate, feature flag, or row count is not wrong to cache -- it is wrong
to cache forever, and without a TTL the only options were caching a stale
answer or not caching at all.

Two things here are easy to get subtly wrong:

**An expired entry must not count as a hit.** Checking freshness after
incrementing `hits` inflates the hit rate with entries that were thrown away,
and hit rate is the number people use to decide whether the cache is working.
Expiries are counted separately, so a low hit rate caused by a short TTL looks
different from one caused by a cold workload.

**An expired entry still occupies capacity.** It is removed when read, but
nothing reads a key that has gone cold -- so a cache can be "full" of entries
that are all dead, and evict a live one to make room. On insert, this evicts
an expired entry in preference to a live one.
"""

from __future__ import annotations

import functools
import threading
import time
from collections.abc import Callable, Hashable
from dataclasses import dataclass
from typing import Any, TypeVar

from .policy import make_policy

T = TypeVar("T")

#: Sentinel marking where positional arguments end and keywords begin, so
#: f(1, b=2) and f(1, 2) get distinct keys.
_KWARG_MARK = object()


@dataclass
class CacheInfo:
    """Snapshot of cache state.

    Mirrors `functools.lru_cache`'s field names so the two are comparable,
    plus `cur_size` (the standard library calls it `currsize`), `expirations`,
    and `evictions`.
    """

    hits: int = 0
    misses: int = 0
    max_size: int | None = 128
    cur_size: int = 0
    evictions: int = 0
    expirations: int = 0
    policy: str = "lru"
    ttl: float | None = None

    @property
    def hit_rate(self) -> float:
        total = self.hits + self.misses
        return self.hits / total if total else 0.0

    def __repr__(self) -> str:
        extra = ""
        if self.ttl is not None:
            extra = f", ttl={self.ttl}, expirations={self.expirations}"
        return (
            f"CacheInfo(hits={self.hits}, misses={self.misses}, "
            f"max_size={self.max_size}, cur_size={self.cur_size}, "
            f"policy={self.policy!r}, evictions={self.evictions}{extra})"
        )


class Unhashable(TypeError):
    """An argument could not be used as a cache key."""


def make_key(args: tuple[Any, ...], kwargs: dict[str, Any]) -> Hashable:
    """Build a hashable key from a call's arguments.

    Types are folded in because `1`, `1.0`, and `True` are all equal and would
    otherwise share a cache entry despite being different calls -- a real
    problem for a function that branches on type.
    """
    key: tuple[Any, ...] = tuple((type(a), a) for a in args)
    if kwargs:
        key += (_KWARG_MARK,)
        # Sorted by name so f(a=1, b=2) and f(b=2, a=1) hit the same entry.
        key += tuple((name, type(v), v) for name, v in sorted(kwargs.items()))
    return key


def cached(
    max_size: int | None = 128,
    *,
    policy: str = "lru",
    ttl: float | None = None,
    clock: Callable[[], float] = time.monotonic,
) -> Callable[[Callable[..., T]], Callable[..., T]]:
    """Memoize a function.

    `max_size=None` caches without bound. `max_size=0` disables caching while
    still counting misses, which matches `functools.lru_cache`.

    `policy` is `"lru"` or `"lfu"`; see `policy.py` for when each one wins.
    `ttl` is a lifetime in seconds, after which an entry is recomputed.

    The clock is `time.monotonic`, not `time.time`: wall-clock time can jump
    backwards when NTP corrects it, which would leave entries alive past their
    TTL, or expire a whole cache at once. It is injectable so that TTL tests
    can advance time instead of sleeping.
    """
    if max_size is not None and max_size < 0:
        raise ValueError("max_size must be non-negative or None")
    if ttl is not None and ttl <= 0:
        raise ValueError("ttl must be positive, or None for no expiry")

    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        cache: dict[Hashable, T] = {}
        #: Only populated when a TTL is set, so the no-TTL path stays free.
        deadlines: dict[Hashable, float] = {}
        evictor = make_policy(policy)
        info = CacheInfo(max_size=max_size, policy=policy, ttl=ttl)
        # A plain dict mutation is not atomic across threads; the lock keeps
        # `cache`, the policy, and `info` from disagreeing under concurrency.
        lock = threading.Lock()

        def _expired(key: Hashable, now: float) -> bool:
            return ttl is not None and deadlines.get(key, 0.0) <= now

        def _drop(key: Hashable) -> None:
            cache.pop(key, None)
            deadlines.pop(key, None)
            evictor.discard(key)

        def _earliest_deadline() -> Hashable | None:
            """The key that expires soonest, in O(1).

            Every entry gets `clock() + ttl` with the same `ttl`, so deadline
            order is insertion order and the front of `deadlines` is the next
            to die. No heap, and no scan -- a linear search for an expired
            entry here would reintroduce the O(n) hit path this project exists
            to document, on a cache that is full and therefore hot.
            """
            return next(iter(deadlines), None)

        def _make_room() -> None:
            """Evict down to `max_size`, preferring already-dead entries."""
            if max_size is None:
                return
            while len(cache) > max_size:
                victim = None
                if ttl is not None:
                    candidate = _earliest_deadline()
                    # An expired entry is free to drop; a live one is not.
                    if candidate is not None and _expired(candidate, clock()):
                        victim = candidate
                        info.expirations += 1
                if victim is None:
                    victim = evictor.evict()
                    info.evictions += 1
                _drop(victim)

        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> T:
            try:
                key = make_key(args, kwargs)
                hash(key)
            except TypeError as exc:
                raise Unhashable(
                    f"{func.__name__}() received an unhashable argument, so the "
                    f"call cannot be cached: {exc}"
                ) from exc

            with lock:
                if key in cache:
                    if _expired(key, clock()):
                        # Not a hit. Counting it as one would inflate the hit
                        # rate with entries that were discarded.
                        info.expirations += 1
                        _drop(key)
                        info.cur_size = len(cache)
                    else:
                        info.hits += 1
                        evictor.touch(key)
                        return cache[key]
                info.misses += 1

            # Computed outside the lock: a slow function must not block every
            # other reader, and that is the whole point of caching it.
            result = func(*args, **kwargs)

            with lock:
                if max_size == 0:
                    return result
                if key in cache:
                    # Another thread filled this key while we computed. Prefer
                    # the stored value so concurrent callers agree.
                    info.cur_size = len(cache)
                    return cache[key]

                cache[key] = result
                evictor.insert(key)
                if ttl is not None:
                    deadlines[key] = clock() + ttl
                _make_room()
                info.cur_size = len(cache)
                # Under LFU the entry just created may already be gone: a new
                # key has frequency 1, so if every other entry has been hit
                # more it is by definition the least frequently used. Return
                # the computed value rather than reading back a key that may
                # no longer be there -- and note the consequence, because it
                # is LFU's real weakness: such a key can never be cached at
                # all, however often it is asked for from now on.
                return result

        def cache_clear() -> None:
            with lock:
                cache.clear()
                deadlines.clear()
                evictor.clear()
                info.hits = info.misses = info.cur_size = 0
                info.evictions = info.expirations = 0

        def cache_invalidate(*args: Any, **kwargs: Any) -> bool:
            """Drop one entry. True if it was there.

            The missing half of a TTL: sometimes you know the answer changed
            and should not have to wait out the lifetime.
            """
            key = make_key(args, kwargs)
            with lock:
                present = key in cache
                _drop(key)
                info.cur_size = len(cache)
                return present

        def cache_purge() -> int:
            """Drop every expired entry and return how many. No-op without a TTL.

            Expired entries are otherwise only noticed when read, so a cache
            of cold keys stays nominally full of dead ones.
            """
            if ttl is None:
                return 0
            with lock:
                now = clock()
                # Insertion order is deadline order, so stop at the first
                # live entry instead of scanning the whole cache.
                dead = []
                for key, deadline in deadlines.items():
                    if deadline > now:
                        break
                    dead.append(key)
                for key in dead:
                    _drop(key)
                info.expirations += len(dead)
                info.cur_size = len(cache)
                return len(dead)

        def cache_keys() -> list[Hashable]:
            """Keys in insertion order. For tests and introspection."""
            with lock:
                return list(cache)

        wrapper.cache_info = info                  # type: ignore[attr-defined]
        wrapper.cache_clear = cache_clear          # type: ignore[attr-defined]
        wrapper.cache_keys = cache_keys            # type: ignore[attr-defined]
        wrapper.cache_invalidate = cache_invalidate  # type: ignore[attr-defined]
        wrapper.cache_purge = cache_purge          # type: ignore[attr-defined]
        wrapper.cache_policy = evictor             # type: ignore[attr-defined]
        return wrapper

    return decorator
