"""Eviction policies.

LRU is the default everywhere, and for good reason -- it exploits temporal
locality and costs nothing to maintain. But it is not always right, and the
project shipped one policy with no evidence it was the right one.

The failure case is a **scan**: walk 10,000 keys once through a 1,000-entry
LRU and every access evicts something still useful, so the hit rate is zero
*and* the cache has thrown away the genuinely hot keys it was holding. LFU
keeps them, because a key accessed 400 times does not lose its place to one
accessed once.

LFU has the opposite failure, and it is worse when it bites: a key that was
hot an hour ago has a frequency count no newly-hot key can catch up to, so it
occupies the cache forever. Neither policy dominates -- which is the point of
`benchmark.compare_policies`, and of reporting both numbers rather than
picking a winner in the abstract.

Both policies are O(1) on the hit, insert, and evict paths. For LFU that is
the interesting part: the naive implementation scans for the minimum frequency
on eviction, which makes the *eviction* path O(n) in exactly the way the
original list-based LRU made the *hit* path O(n).

The one exception is `LFUPolicy.discard`, which may have to recompute the
minimum frequency and is O(distinct frequencies). It is called on explicit
invalidation and TTL expiry, never on a hit, so it is off the path that
matters -- but it is not O(1) and pretending otherwise would be the same
mistake this project exists to document.
"""

from __future__ import annotations

from collections.abc import Hashable
from typing import Protocol


class Policy(Protocol):
    """What the cache needs from an eviction policy. All methods are O(1)."""

    def touch(self, key: Hashable) -> None:
        """Record a hit on an existing key."""

    def insert(self, key: Hashable) -> None:
        """Record a newly added key."""

    def discard(self, key: Hashable) -> None:
        """Forget a key that has been removed from the cache."""

    def evict(self) -> Hashable:
        """Name the key that should go. Raises KeyError when empty."""

    def clear(self) -> None: ...


class LRUPolicy:
    """Least recently used.

    Recency lives in a dict used as an ordered set. Since Python 3.7 dicts
    preserve insertion order, so "move to most-recently-used" is a delete plus
    a reinsert -- both O(1) -- and the least-recently-used key is simply the
    first one. No linked list, no list scan.
    """

    name = "lru"

    def __init__(self) -> None:
        self._order: dict[Hashable, None] = {}

    def touch(self, key: Hashable) -> None:
        del self._order[key]
        self._order[key] = None

    def insert(self, key: Hashable) -> None:
        self._order[key] = None

    def discard(self, key: Hashable) -> None:
        self._order.pop(key, None)

    def evict(self) -> Hashable:
        return next(iter(self._order))

    def clear(self) -> None:
        self._order.clear()


class LFUPolicy:
    """Least frequently used, O(1) on every path.

    Keys are bucketed by access count, and `_min_freq` tracks the lowest
    non-empty bucket so eviction never searches for it. Each bucket is itself
    a dict-as-ordered-set, which breaks frequency ties by recency -- without
    that, a bucket of equally-cold keys would evict arbitrarily, and a scan
    through 10,000 single-access keys could evict the one that is about to be
    read again.

    Maintaining `_min_freq` is the whole trick. It can only move in two ways:
    up by one, when the last key leaves the minimum bucket via `touch`; or
    down to 1, when a key is inserted. Anything else and eviction would be
    reading from an empty bucket, or from the wrong one.
    """

    name = "lfu"

    def __init__(self) -> None:
        self._freq: dict[Hashable, int] = {}
        self._buckets: dict[int, dict[Hashable, None]] = {}
        self._min_freq = 0

    def touch(self, key: Hashable) -> None:
        old = self._freq[key]
        new = old + 1
        self._freq[key] = new

        bucket = self._buckets[old]
        del bucket[key]
        if not bucket:
            del self._buckets[old]
            # The minimum bucket just emptied, and the only key that left it
            # went to old+1, so that is the new minimum.
            if self._min_freq == old:
                self._min_freq = new

        self._buckets.setdefault(new, {})[key] = None

    def insert(self, key: Hashable) -> None:
        self._freq[key] = 1
        self._buckets.setdefault(1, {})[key] = None
        self._min_freq = 1

    def discard(self, key: Hashable) -> None:
        freq = self._freq.pop(key, None)
        if freq is None:
            return
        bucket = self._buckets[freq]
        del bucket[key]
        if not bucket:
            del self._buckets[freq]
            if self._min_freq == freq:
                # Nothing left at this frequency, and unlike `touch` there is
                # no key that moved up to tell us where the minimum went, so
                # it has to be recomputed. O(distinct frequencies), and off
                # the hot path -- see the module docstring.
                self._min_freq = min(self._buckets, default=0)

    def evict(self) -> Hashable:
        if not self._buckets:
            raise KeyError("nothing to evict")
        bucket = self._buckets[self._min_freq]
        return next(iter(bucket))

    def clear(self) -> None:
        self._freq.clear()
        self._buckets.clear()
        self._min_freq = 0

    def frequency(self, key: Hashable) -> int:
        """Access count for a key. For tests and introspection."""
        return self._freq.get(key, 0)


POLICIES: dict[str, type] = {"lru": LRUPolicy, "lfu": LFUPolicy}


def make_policy(name: str) -> Policy:
    try:
        return POLICIES[name]()
    except KeyError:
        raise ValueError(
            f"unknown policy {name!r}; choose from {sorted(POLICIES)}"
        ) from None
