"""Eviction policies, TTL expiry, and the generic `cached` decorator."""

from __future__ import annotations

import threading

import pytest

from fastcache import LFUPolicy, LRUPolicy, Unhashable, cached, make_policy
from fastcache.benchmark import (
    hot_set_with_scans,
    scan_workload,
    shifting_hot_set,
    zipf_workload,
)


class FakeClock:
    """A clock you advance instead of sleeping on."""

    def __init__(self, now: float = 1000.0) -> None:
        self.now = now

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


# --------------------------------------------------------------------------- #
# LRU policy
# --------------------------------------------------------------------------- #


def test_lru_evicts_the_least_recently_used():
    p = LRUPolicy()
    for key in "abc":
        p.insert(key)
    assert p.evict() == "a"
    p.touch("a")
    assert p.evict() == "b"


def test_lru_discard_forgets_a_key():
    p = LRUPolicy()
    for key in "abc":
        p.insert(key)
    p.discard("a")
    assert p.evict() == "b"
    # Discarding twice is not an error: the cache may have dropped it already.
    p.discard("a")


# --------------------------------------------------------------------------- #
# LFU policy
# --------------------------------------------------------------------------- #


def test_lfu_evicts_the_least_frequently_used():
    p = LFUPolicy()
    for key in "abc":
        p.insert(key)
    p.touch("a")
    p.touch("a")
    p.touch("b")
    assert p.evict() == "c"


def test_lfu_breaks_frequency_ties_by_recency():
    """Without this, a scan of equally-cold keys evicts arbitrarily."""
    p = LFUPolicy()
    for key in "abc":
        p.insert(key)
    # All at frequency 1. The oldest should go.
    assert p.evict() == "a"


def test_lfu_tracks_frequencies():
    p = LFUPolicy()
    p.insert("a")
    assert p.frequency("a") == 1
    p.touch("a")
    p.touch("a")
    assert p.frequency("a") == 3
    assert p.frequency("missing") == 0


def test_lfu_min_frequency_survives_the_minimum_bucket_emptying():
    """The bookkeeping that makes eviction O(1) instead of a scan."""
    p = LFUPolicy()
    p.insert("a")
    p.insert("b")
    p.touch("a")          # a -> 2, min stays 1 because b is still there
    assert p.evict() == "b"
    p.touch("b")          # b -> 2, bucket 1 is now empty, min must become 2
    assert p.evict() in {"a", "b"}
    p.touch("a")          # a -> 3
    assert p.evict() == "b"


def test_lfu_min_frequency_survives_a_discard():
    p = LFUPolicy()
    p.insert("a")
    p.insert("b")
    p.touch("b")
    p.touch("b")
    p.discard("a")        # empties the minimum bucket with no key moving up
    assert p.evict() == "b"


def test_evicting_from_an_empty_policy_raises():
    with pytest.raises(KeyError):
        LFUPolicy().evict()


def test_clearing_resets_a_policy():
    p = LFUPolicy()
    p.insert("a")
    p.touch("a")
    p.clear()
    assert p.frequency("a") == 0
    with pytest.raises(KeyError):
        p.evict()


def test_unknown_policy_names_are_rejected():
    with pytest.raises(ValueError, match="unknown policy"):
        make_policy("mru")


# --------------------------------------------------------------------------- #
# The policy actually changes what the cache keeps
# --------------------------------------------------------------------------- #


def cached_args(fn) -> set:
    """The bare argument behind each cache key, for readable assertions."""
    return {key[0][1] for key in fn.cache_keys()}


def test_lfu_keeps_a_hot_key_that_lru_would_drop():
    """The reason LFU exists, in five calls."""
    for policy, survives in (("lru", False), ("lfu", True)):
        fn = cached(2, policy=policy)(lambda n: n)
        fn(1)
        fn(1)
        fn(1)          # key 1 is clearly the hot one
        fn(2)
        fn(3)          # cache is full; something must go
        assert (1 in cached_args(fn)) is survives


def test_lfu_can_refuse_to_admit_a_new_key():
    """LFU's real weakness, and it is permanent.

    A new key has frequency 1. If every entry has been hit more often, the new
    key is by definition the least frequently used thing in the cache -- so it
    is evicted immediately and can never be cached, however often it is asked
    for from now on.
    """
    fn = cached(2, policy="lfu")(lambda n: n)
    for _ in range(5):
        fn(1)
        fn(2)
    assert fn(99) == 99            # still returns the right answer
    assert 99 not in cached_args(fn)
    assert fn.cache_info.evictions >= 1


def test_the_default_policy_is_lru():
    fn = cached(4)(lambda n: n)
    assert fn.cache_info.policy == "lru"


# --------------------------------------------------------------------------- #
# TTL
# --------------------------------------------------------------------------- #


def test_an_expired_entry_is_recomputed():
    clock = FakeClock()
    calls = []
    fn = cached(8, ttl=10, clock=clock)(lambda n: calls.append(n) or n)

    fn(1)
    fn(1)
    assert calls == [1]
    clock.advance(11)
    fn(1)
    assert calls == [1, 1]


def test_an_expired_entry_is_not_counted_as_a_hit():
    """Counting it would inflate the number people trust the cache by."""
    clock = FakeClock()
    fn = cached(8, ttl=10, clock=clock)(lambda n: n)
    fn(1)
    clock.advance(11)
    fn(1)
    info = fn.cache_info
    assert (info.hits, info.misses, info.expirations) == (0, 2, 1)
    assert info.hit_rate == 0.0


def test_an_entry_inside_its_ttl_is_a_hit():
    clock = FakeClock()
    fn = cached(8, ttl=10, clock=clock)(lambda n: n)
    fn(1)
    clock.advance(9)
    fn(1)
    assert fn.cache_info.hits == 1


def test_the_ttl_clock_is_monotonic_by_default():
    """Wall-clock time can jump backwards when NTP corrects it."""
    import time as time_module

    fn = cached(8, ttl=10)(lambda n: n)
    assert fn.cache_info.ttl == 10
    # Not asserting on time itself -- just that a real run does not expire.
    fn(1)
    fn(1)
    assert fn.cache_info.hits == 1
    assert time_module.monotonic() > 0


def test_purging_reclaims_space_that_nothing_reads():
    """An expired entry is only noticed when read, and cold keys never are."""
    clock = FakeClock()
    fn = cached(8, ttl=10, clock=clock)(lambda n: n)
    for i in range(5):
        fn(i)
    assert fn.cache_info.cur_size == 5

    clock.advance(11)
    # Still nominally full of entries that are all dead.
    assert len(fn.cache_keys()) == 5
    assert fn.cache_purge() == 5
    assert fn.cache_info.cur_size == 0
    assert fn.cache_purge() == 0


def test_purging_without_a_ttl_is_a_noop():
    fn = cached(8)(lambda n: n)
    fn(1)
    assert fn.cache_purge() == 0
    assert fn.cache_info.cur_size == 1


def test_a_full_cache_evicts_a_dead_entry_before_a_live_one():
    """Otherwise a cache full of corpses evicts the entry you are using."""
    clock = FakeClock()
    fn = cached(3, ttl=10, clock=clock)(lambda n: n)
    fn(1)
    fn(2)
    clock.advance(11)     # 1 and 2 are now dead
    fn(3)                 # live
    fn(4)                 # cache is over size; a dead entry should go
    keys = cached_args(fn)
    assert 3 in keys and 4 in keys
    assert fn.cache_info.expirations >= 1


def test_a_non_positive_ttl_is_rejected():
    for bad in (0, -1):
        with pytest.raises(ValueError, match="ttl must be positive"):
            cached(8, ttl=bad)


def test_no_ttl_means_no_expiry():
    fn = cached(8)(lambda n: n)
    assert fn.cache_info.ttl is None
    fn(1)
    fn(1)
    assert fn.cache_info.hits == 1


# --------------------------------------------------------------------------- #
# Invalidation
# --------------------------------------------------------------------------- #


def test_invalidating_one_entry_leaves_the_rest():
    calls = []
    fn = cached(8)(lambda n: calls.append(n) or n)
    fn(1)
    fn(2)
    assert fn.cache_invalidate(1) is True
    fn(1)
    fn(2)
    assert calls == [1, 2, 1]


def test_invalidating_a_missing_entry_reports_false():
    fn = cached(8)(lambda n: n)
    assert fn.cache_invalidate(42) is False


def test_invalidation_keeps_the_policy_in_step():
    """A policy still holding an evicted key would name a phantom victim."""
    fn = cached(2, policy="lfu")(lambda n: n)
    fn(1)
    fn(1)
    fn(2)
    fn.cache_invalidate(1)
    fn(3)
    assert fn.cache_info.cur_size <= 2


# --------------------------------------------------------------------------- #
# Shared contract with lru_cache
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("policy", ["lru", "lfu"])
def test_cached_memoizes(policy):
    calls = []
    fn = cached(8, policy=policy)(lambda n: calls.append(n) or n * 2)
    assert fn(3) == 6
    assert fn(3) == 6
    assert calls == [3]


@pytest.mark.parametrize("policy", ["lru", "lfu"])
def test_max_size_is_respected(policy):
    fn = cached(3, policy=policy)(lambda n: n)
    for i in range(20):
        fn(i)
    assert fn.cache_info.cur_size <= 3


@pytest.mark.parametrize("policy", ["lru", "lfu"])
def test_unbounded_caches_never_evict(policy):
    fn = cached(None, policy=policy)(lambda n: n)
    for i in range(200):
        fn(i)
    assert fn.cache_info.cur_size == 200
    assert fn.cache_info.evictions == 0


@pytest.mark.parametrize("policy", ["lru", "lfu"])
def test_zero_max_size_disables_caching_but_counts_misses(policy):
    fn = cached(0, policy=policy)(lambda n: n)
    fn(1)
    fn(1)
    assert (fn.cache_info.hits, fn.cache_info.misses) == (0, 2)
    assert fn.cache_info.cur_size == 0


def test_a_negative_max_size_is_rejected():
    with pytest.raises(ValueError, match="non-negative"):
        cached(-1)


def test_unhashable_arguments_raise_a_clear_error():
    fn = cached(8)(lambda n: n)
    with pytest.raises(Unhashable, match="cannot be cached"):
        fn([1, 2])


def test_clearing_resets_every_counter():
    fn = cached(2, policy="lfu")(lambda n: n)
    for i in range(10):
        fn(i)
    fn.cache_clear()
    info = fn.cache_info
    assert (info.hits, info.misses, info.cur_size, info.evictions) == (0, 0, 0, 0)
    fn(1)
    assert info.misses == 1


def test_the_repr_mentions_the_policy_and_ttl():
    fn = cached(4, policy="lfu", ttl=30)(lambda n: n)
    fn(1)
    text = repr(fn.cache_info)
    assert "policy='lfu'" in text and "ttl=30" in text


@pytest.mark.parametrize("policy", ["lru", "lfu"])
def test_concurrent_callers_agree_on_the_value(policy):
    fn = cached(64, policy=policy)(lambda n: n * 3)
    # Record the argument alongside the answer: eight threads append to one
    # list, so position says nothing about which call produced which value.
    seen: list[tuple[int, int]] = []

    def worker():
        for i in range(200):
            arg = i % 32
            seen.append((arg, fn(arg)))

    threads = [threading.Thread(target=worker) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(seen) == 8 * 200
    assert all(value == arg * 3 for arg, value in seen)
    assert fn.cache_info.cur_size <= 64


# --------------------------------------------------------------------------- #
# The workload comparison has to actually show what the README claims
# --------------------------------------------------------------------------- #


def test_lfu_beats_lru_when_scans_flush_a_stable_hot_set():
    from fastcache.benchmark import replay

    trace = hot_set_with_scans(2_000, 20_000, 200)
    lru_hit, _ = replay(trace, 200, "lru")
    lfu_hit, _ = replay(trace, 200, "lfu")
    assert lfu_hit > lru_hit + 0.05


def test_lru_beats_lfu_when_the_hot_set_moves():
    from fastcache.benchmark import replay

    trace = shifting_hot_set(2_000, 20_000, 200)
    lru_hit, _ = replay(trace, 200, "lru")
    lfu_hit, _ = replay(trace, 200, "lfu")
    assert lru_hit > lfu_hit + 0.5


def test_a_scan_defeats_both_policies():
    from fastcache.benchmark import replay

    trace = scan_workload(2_000, 20_000, 200)
    assert replay(trace, 200, "lru")[0] == 0.0
    assert replay(trace, 200, "lfu")[0] == 0.0


def test_the_zipf_workload_is_actually_skewed():
    trace = zipf_workload(2_000, 20_000, 200)
    top = sum(1 for k in trace if k < 20)
    assert top / len(trace) > 0.3
