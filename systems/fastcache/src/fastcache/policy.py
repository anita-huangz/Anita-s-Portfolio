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

from .sketch import CountMinSketch


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


class TinyLFUPolicy:
    """Window-TinyLFU: an admission filter over a segmented LRU.

    Plain LFU has one failure and it is severe. A key that was hot an hour ago
    keeps a count nothing new can reach, so the cache freezes around a working
    set that has moved on -- `compare_policies` measures this directly, and on
    a shifting hot set LFU holds 10.7% against LRU's 96.4%. Two separate things
    cause that, and fixing one without the other does not help:

    **Counts never decay.** The sketch ages, halving every counter once the
    workload has been sampled enough. Yesterday's champion fades instead of
    holding its slot forever.

    **A new key cannot get in.** Under LFU a fresh key has frequency 1, so if
    everything resident has been touched more it is by definition the least
    frequently used and goes straight back out -- however often it is asked for
    afterwards. The admission window fixes that: every new key is *always*
    admitted, to a small LRU at the front, and only has to prove itself when it
    is pushed out of that window.

    The layout, following Caffeine:

        window (1%)  ->  probation (20% of main)  ->  protected (80% of main)

    New keys enter the window. When the window overflows, its oldest key
    becomes a *candidate* and competes with the main region's victim on
    estimated frequency; the loser leaves the cache. A hit in probation
    promotes to protected, and protected overflow falls back to probation --
    that is the segmented LRU, and it is what keeps a key that was merely
    admitted from displacing one that has proven itself.

    The sketch is what makes admission possible at all. Frequencies for keys
    the cache does *not* hold cannot live beside the entries, because there are
    no entries -- see `sketch.py`.
    """

    name = "tinylfu"

    #: Share of capacity held in the admission window.
    WINDOW_FRACTION = 0.01
    #: Share of the main region that is protected rather than on probation.
    PROTECTED_FRACTION = 0.8

    def __init__(
        self, capacity: int | None = None, window_fraction: float | None = None
    ) -> None:
        # With no bound there is nothing to evict, so the sizes are nominal and
        # only the sketch does any work.
        size = capacity if capacity and capacity > 0 else 1
        fraction = self.WINDOW_FRACTION if window_fraction is None else window_fraction
        if not 0 < fraction < 1:
            raise ValueError("window_fraction must be between 0 and 1")
        self.window_fraction = fraction
        self._sketch = CountMinSketch(size)
        self._window_target = max(1, int(size * fraction))
        main = max(1, size - self._window_target)
        self._protected_target = max(1, int(main * self.PROTECTED_FRACTION))

        self._window: dict[Hashable, None] = {}
        self._probation: dict[Hashable, None] = {}
        self._protected: dict[Hashable, None] = {}

    # -- helpers ----------------------------------------------------------

    @staticmethod
    def _oldest(segment: dict[Hashable, None]) -> Hashable:
        return next(iter(segment))

    @staticmethod
    def _bump(segment: dict[Hashable, None], key: Hashable) -> None:
        """Move an existing key to the most-recent end."""
        del segment[key]
        segment[key] = None

    # -- policy protocol --------------------------------------------------

    def touch(self, key: Hashable) -> None:
        self._sketch.increment(key)
        if key in self._window:
            self._bump(self._window, key)
        elif key in self._probation:
            # Proven itself once: move out of probation into protected, and
            # push protected's oldest back down if that overflows.
            del self._probation[key]
            self._protected[key] = None
            while len(self._protected) > self._protected_target:
                demoted = self._oldest(self._protected)
                del self._protected[demoted]
                self._probation[demoted] = None
        elif key in self._protected:
            self._bump(self._protected, key)

    def insert(self, key: Hashable) -> None:
        self._sketch.increment(key)
        self._window[key] = None

    def discard(self, key: Hashable) -> None:
        for segment in (self._window, self._probation, self._protected):
            if key in segment:
                del segment[key]
                return

    def evict(self) -> Hashable:
        if not (self._window or self._probation or self._protected):
            raise KeyError("nothing to evict")

        # Drain the window down to its target first. The last key demoted is
        # the admission candidate: it is the one that has just been asked to
        # justify a place in the main region.
        candidate: Hashable | None = None
        while len(self._window) > self._window_target and (
            self._probation or self._protected or len(self._window) > 1
        ):
            candidate = self._oldest(self._window)
            del self._window[candidate]
            self._probation[candidate] = None

        if self._probation:
            victim = self._oldest(self._probation)
            segment = self._probation
        elif self._protected:
            victim = self._oldest(self._protected)
            segment = self._protected
        else:
            victim = self._oldest(self._window)
            segment = self._window

        # Admission: the newcomer only displaces the resident if it has been
        # seen more often. On a tie the resident stays, because it has already
        # paid the cost of being fetched.
        contested = (
            candidate is not None
            and candidate is not victim
            and candidate in self._probation
        )
        if contested and self._sketch.estimate(candidate) < self._sketch.estimate(victim):
            victim, segment = candidate, self._probation

        del segment[victim]
        return victim

    def clear(self) -> None:
        self._window.clear()
        self._probation.clear()
        self._protected.clear()
        self._sketch.clear()

    # -- introspection ----------------------------------------------------

    def frequency(self, key: Hashable) -> int:
        """Estimated access count, including keys the cache no longer holds."""
        return self._sketch.estimate(key)

    @property
    def segments(self) -> dict[str, int]:
        return {
            "window": len(self._window),
            "probation": len(self._probation),
            "protected": len(self._protected),
        }

    @property
    def halvings(self) -> int:
        """How many times history has been aged. Zero means no decay happened."""
        return self._sketch.halvings

    @property
    def sketch_bytes(self) -> int:
        return self._sketch.bytes_used

POLICIES: dict[str, type] = {
    "lru": LRUPolicy,
    "lfu": LFUPolicy,
    "tinylfu": TinyLFUPolicy,
}


def make_policy(name: str, capacity: int | None = None) -> Policy:
    """Build a policy. `capacity` is only used by policies that size on it.

    TinyLFU needs it: the admission window and the sketch are both fractions
    of the cache size, and a policy that has to guess its own capacity would
    size them wrong. LRU and LFU take no argument and ignore it.
    """
    try:
        cls = POLICIES[name]
    except KeyError:
        raise ValueError(
            f"unknown policy {name!r}; choose from {sorted(POLICIES)}"
        ) from None
    if cls is TinyLFUPolicy:
        return cls(capacity)
    return cls()
