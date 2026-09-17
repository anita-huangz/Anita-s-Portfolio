"""An LRU cache decorator with O(1) lookup, insert, and eviction.

The original stored recency in a list and did `keys.remove(key)` on every hit.
`list.remove` is a linear scan, so the *hit* path -- the path the whole cache
exists to make fast -- was O(n) in the cache size. At max_size=128 that is a
128-element scan to answer a question the dict already answered in O(1).

This version keeps recency in the dict itself. Since Python 3.7 dicts preserve
insertion order, so "move to most-recently-used" is a delete plus a reinsert,
both O(1), and the least-recently-used entry is simply the first key.
"""

from __future__ import annotations

import functools
import threading
from collections.abc import Callable, Hashable
from dataclasses import dataclass
from typing import Any, TypeVar

T = TypeVar("T")

#: Sentinel marking where positional arguments end and keywords begin, so
#: f(1, b=2) and f(1, 2) get distinct keys.
_KWARG_MARK = object()


@dataclass
class CacheInfo:
    """Snapshot of cache state.

    Mirrors `functools.lru_cache`'s field names so the two are comparable,
    plus `cur_size` which the standard library exposes as `currsize`.
    """

    hits: int = 0
    misses: int = 0
    max_size: int | None = 128
    cur_size: int = 0

    @property
    def hit_rate(self) -> float:
        total = self.hits + self.misses
        return self.hits / total if total else 0.0

    def __repr__(self) -> str:
        return (
            f"CacheInfo(hits={self.hits}, misses={self.misses}, "
            f"max_size={self.max_size}, cur_size={self.cur_size})"
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


def lru_cache(max_size: int | None = 128) -> Callable[[Callable[..., T]], Callable[..., T]]:
    """Memoize a function, evicting the least recently used entry when full.

    `max_size=None` caches without bound. `max_size=0` disables caching while
    still counting misses, which matches `functools.lru_cache`.
    """
    if max_size is not None and max_size < 0:
        raise ValueError("max_size must be non-negative or None")

    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        cache: dict[Hashable, T] = {}
        info = CacheInfo(max_size=max_size)
        # A plain dict mutation is not atomic across threads; the lock keeps
        # `cache` and `info` from disagreeing under concurrent calls.
        lock = threading.Lock()

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
                    info.hits += 1
                    # Move to most-recently-used: O(1), no list scan.
                    value = cache.pop(key)
                    cache[key] = value
                    return value
                info.misses += 1

            # Computed outside the lock: a slow function must not block every
            # other reader, and that is the whole point of caching it.
            result = func(*args, **kwargs)

            with lock:
                if max_size == 0:
                    return result
                # Another thread may have filled this key while we computed.
                if key not in cache:
                    cache[key] = result
                    if max_size is not None and len(cache) > max_size:
                        # First key is the least recently used.
                        cache.pop(next(iter(cache)))
                info.cur_size = len(cache)
                return cache[key]

        def cache_clear() -> None:
            with lock:
                cache.clear()
                info.hits = info.misses = info.cur_size = 0

        def cache_keys() -> list[Hashable]:
            """Keys in LRU order, oldest first. For tests and introspection."""
            with lock:
                return list(cache)

        wrapper.cache_info = info          # type: ignore[attr-defined]
        wrapper.cache_clear = cache_clear  # type: ignore[attr-defined]
        wrapper.cache_keys = cache_keys    # type: ignore[attr-defined]
        return wrapper

    return decorator
