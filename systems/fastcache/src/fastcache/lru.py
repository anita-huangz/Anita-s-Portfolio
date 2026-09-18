"""An LRU cache decorator with O(1) lookup, insert, and eviction.

The original stored recency in a list and did `keys.remove(key)` on every hit.
`list.remove` is a linear scan, so the *hit* path -- the path the whole cache
exists to make fast -- was O(n) in the cache size. At max_size=128 that is a
128-element scan to answer a question the dict already answered in O(1).

This version keeps recency in the dict itself. Since Python 3.7 dicts preserve
insertion order, so "move to most-recently-used" is a delete plus a reinsert,
both O(1), and the least-recently-used entry is simply the first key.

This is the specialised LRU path, kept alongside the general `cached` decorator in
`cache.py` because generality is not free: routing LRU through a policy object
costs one extra method call per hit, measured at 0.43 -> 0.54 us, about 25%.
Both are flat in the cache size, which is the property that matters -- but if
you want LRU and nothing else, this is the one to use. Everything shared
(`make_key`, `CacheInfo`) is defined once, in `cache.py`.
"""

from __future__ import annotations

import functools
import threading
from collections.abc import Callable, Hashable
from typing import Any, TypeVar

# One definition of each, shared with the general `cached` decorator. Two
# copies of `make_key` would be two chances to key a call differently, and the
# bug would look like a cache miss rather than a bug.
from .cache import CacheInfo, Unhashable, make_key

T = TypeVar("T")

__all__ = ["CacheInfo", "Unhashable", "lru_cache", "make_key"]


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
