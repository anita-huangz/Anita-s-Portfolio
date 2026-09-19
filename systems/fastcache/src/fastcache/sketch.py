"""A count-min sketch with aging: frequency for keys the cache does not hold.

This is the piece that makes TinyLFU possible, and the reason it is not simply
LFU with a timer. An LFU policy can only know the frequency of keys it is
currently storing, because the count lives beside the entry. So it cannot
answer the question admission control actually needs to ask:

    this key is not in the cache, and something has to go --
    has the newcomer been requested more often than my victim?

A sketch answers that for every key ever seen, in a **fixed** amount of memory,
by giving up exactness. Four hash positions per key, and the estimate is the
smallest of the four counters. Collisions can only push a count *up*, never
down, so the minimum is an upper bound that is usually tight -- a key that
looks rare really is rare, which is the direction that matters when deciding
what to throw away.

Counters are four bits, packed two to a byte. That is not a micro-optimisation:
the whole argument for a sketch over a dictionary of counts is bounded memory,
and a dictionary would grow with the number of distinct keys, which is exactly
the thing being avoided. Four bits saturate at 15, which is enough -- the
question is "more or less often", not "how many times".

**Aging is the point.** Every `sample_size` increments, all counters are
halved. Without it a key that was hot an hour ago keeps a count nothing new can
beat, and the cache is frozen around a working set that has moved on. Halving
costs one pass over a fixed array and lets history decay by design rather than
by restart.

Reference: Einziger, Friedman & Manes, *TinyLFU: A Highly Efficient Cache
Admission Policy* (2017).
"""

from __future__ import annotations

from collections.abc import Hashable

#: Four-bit counters: 0-15. High enough to rank keys, low enough that the whole
#: sketch stays small.
MAX_COUNT = 15

#: Hash positions per key. Four is the standard choice; more positions make
#: collisions rarer and the sketch proportionally bigger.
DEPTH = 4

#: Multiplied by capacity to decide how many increments trigger a halving.
#: Ten means roughly ten accesses per cache slot before history decays.
SAMPLE_FACTOR = 10


def _next_power_of_two(value: int) -> int:
    size = 1
    while size < value:
        size <<= 1
    return size


class CountMinSketch:
    """Approximate access counts in fixed memory, with periodic decay."""

    def __init__(self, capacity: int, depth: int = DEPTH) -> None:
        if capacity < 1:
            raise ValueError("capacity must be at least 1")
        self.depth = depth
        # Rounded to a power of two so the position can be masked rather than
        # taken modulo, which matters on a path this hot.
        self.width = _next_power_of_two(max(capacity * 8, 16))
        self._mask = self.width - 1
        # Two counters per byte.
        self._table = bytearray(self.width * depth // 2)
        self.sample_size = SAMPLE_FACTOR * capacity
        self.increments = 0
        self.halvings = 0

    @property
    def bytes_used(self) -> int:
        return len(self._table)

    def _positions(self, key: Hashable) -> list[int]:
        """One index per row, spread by mixing the hash differently each time."""
        base = hash(key)
        out = []
        for row in range(self.depth):
            # A cheap independent-ish hash per row. Multiplying by distinct odd
            # constants and folding the high bits down decorrelates the rows,
            # which is what stops one unlucky key colliding in all four.
            mixed = (base ^ (base >> 16)) * (0x9E3779B1 + row * 0x85EBCA6B)
            mixed &= 0xFFFFFFFFFFFFFFFF
            mixed ^= mixed >> 13
            out.append(row * self.width + (mixed & self._mask))
        return out

    def _get(self, index: int) -> int:
        byte = self._table[index >> 1]
        return byte & 0x0F if index & 1 == 0 else byte >> 4

    def _set(self, index: int, value: int) -> None:
        slot = index >> 1
        byte = self._table[slot]
        if index & 1 == 0:
            self._table[slot] = (byte & 0xF0) | value
        else:
            self._table[slot] = (byte & 0x0F) | (value << 4)

    def increment(self, key: Hashable) -> None:
        """Record one access, and age the whole sketch if it is time."""
        grew = False
        for index in self._positions(key):
            current = self._get(index)
            if current < MAX_COUNT:
                self._set(index, current + 1)
                grew = True
        # Only a counter that actually moved counts toward the next halving.
        # Otherwise a single saturated key hammered in a loop would age the
        # whole sketch on its own.
        if grew:
            self.increments += 1
            if self.increments >= self.sample_size:
                self.halve()

    def estimate(self, key: Hashable) -> int:
        """Approximate access count. Never an underestimate."""
        return min(self._get(index) for index in self._positions(key))

    def halve(self) -> None:
        """Divide every counter by two. This is the aging step."""
        table = self._table
        for i in range(len(table)):
            # Both nibbles at once: >>1 shifts each counter down, and the mask
            # clears the bit that would otherwise leak from the high nibble
            # into the low one.
            table[i] = (table[i] >> 1) & 0x77
        self.increments = 0
        self.halvings += 1

    def clear(self) -> None:
        self._table = bytearray(len(self._table))
        self.increments = 0
        self.halvings = 0
