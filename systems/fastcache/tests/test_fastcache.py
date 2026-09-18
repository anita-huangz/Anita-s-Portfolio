"""Tests for caching, eviction order, keying, and the decorator contract."""

from __future__ import annotations

import threading

import pytest

from fastcache import Unhashable, lru_cache, make_key


def counting(fn):
    """Wrap a function so the test can see how often it really ran."""

    def wrapped(*args, **kwargs):
        wrapped.calls += 1
        return fn(*args, **kwargs)

    wrapped.calls = 0
    wrapped.__name__ = getattr(fn, "__name__", "wrapped")
    return wrapped


# --------------------------------------------------------------------------- #
# Caching basics
# --------------------------------------------------------------------------- #


def test_repeated_call_is_computed_once():
    add = lru_cache(10)(counting(lambda a, b: a + b))
    assert add(1, 2) == 3
    assert add(1, 2) == 3
    assert add.__wrapped__.calls == 1


def test_different_arguments_are_computed_separately():
    add = lru_cache(10)(counting(lambda a, b: a + b))
    add(1, 2)
    add(2, 1)
    assert add.__wrapped__.calls == 2


def test_keyword_arguments_are_cached():
    add = lru_cache(10)(counting(lambda a, b: a + b))
    assert add(a=1, b=2) == 3
    assert add(a=1, b=2) == 3
    assert add.__wrapped__.calls == 1


def test_keyword_order_does_not_matter():
    add = lru_cache(10)(counting(lambda a, b: a + b))
    add(a=1, b=2)
    add(b=2, a=1)
    assert add.__wrapped__.calls == 1


def test_positional_and_keyword_forms_are_distinct_keys():
    """f(1, 2) and f(1, b=2) are different call shapes; keys must not collide."""
    assert make_key((1, 2), {}) != make_key((1,), {"b": 2})


def test_types_are_part_of_the_key():
    """1, 1.0 and True are all equal -- a type-branching function needs them apart."""
    fn = lru_cache(10)(counting(lambda x: type(x).__name__))
    assert fn(1) == "int"
    assert fn(1.0) == "float"
    assert fn(True) == "bool"
    assert fn.__wrapped__.calls == 3


def test_unhashable_argument_raises_a_clear_error():
    fn = lru_cache(10)(lambda items: len(items))
    with pytest.raises(Unhashable, match="unhashable"):
        fn([1, 2, 3])


# --------------------------------------------------------------------------- #
# Eviction
# --------------------------------------------------------------------------- #


def test_cache_never_exceeds_max_size():
    fn = lru_cache(3)(lambda n: n)
    for i in range(10):
        fn(i)
    assert len(fn.cache_keys()) == 3
    assert fn.cache_info.cur_size == 3


def test_the_least_recently_used_entry_is_evicted():
    fn = lru_cache(3)(counting(lambda n: n))
    fn(1), fn(2), fn(3)
    fn(4)                      # evicts 1, the oldest
    fn.__wrapped__.calls = 0
    fn(2), fn(3), fn(4)        # all still cached
    assert fn.__wrapped__.calls == 0
    fn(1)                      # was evicted
    assert fn.__wrapped__.calls == 1


def test_a_hit_refreshes_recency():
    """The point of LRU: using an entry protects it from the next eviction."""
    fn = lru_cache(3)(counting(lambda n: n))
    fn(1), fn(2), fn(3)
    fn(1)                      # 1 becomes most recent, so 2 is now oldest
    fn(4)                      # evicts 2, not 1
    fn.__wrapped__.calls = 0
    fn(1)
    assert fn.__wrapped__.calls == 0     # 1 survived
    fn(2)
    assert fn.__wrapped__.calls == 1     # 2 was evicted


def test_keys_are_reported_oldest_first():
    fn = lru_cache(3)(lambda n: n)
    fn(1), fn(2), fn(3)
    fn(1)
    assert fn.cache_keys() == [
        make_key((2,), {}), make_key((3,), {}), make_key((1,), {})
    ]


def test_unbounded_cache_never_evicts():
    fn = lru_cache(None)(lambda n: n)
    for i in range(500):
        fn(i)
    assert fn.cache_info.cur_size == 500


def test_zero_size_disables_caching_but_still_counts():
    fn = lru_cache(0)(counting(lambda n: n))
    fn(1), fn(1)
    assert fn.__wrapped__.calls == 2
    assert fn.cache_info.misses == 2
    assert fn.cache_info.cur_size == 0


def test_negative_size_is_rejected():
    with pytest.raises(ValueError, match="non-negative"):
        lru_cache(-1)


# --------------------------------------------------------------------------- #
# CacheInfo
# --------------------------------------------------------------------------- #


def test_hits_and_misses_are_counted():
    fn = lru_cache(10)(lambda n: n)
    fn(1)       # miss
    fn(1)       # hit
    fn(2)       # miss
    assert (fn.cache_info.hits, fn.cache_info.misses) == (1, 2)


def test_hit_rate():
    fn = lru_cache(10)(lambda n: n)
    fn(1), fn(1), fn(1), fn(2)
    assert fn.cache_info.hit_rate == pytest.approx(0.5)


def test_hit_rate_of_an_unused_cache_is_zero_not_a_division_error():
    fn = lru_cache(10)(lambda n: n)
    assert fn.cache_info.hit_rate == 0.0


def test_cache_info_repr_is_readable():
    fn = lru_cache(5)(lambda n: n)
    fn(1)
    text = repr(fn.cache_info)
    assert "hits=0" in text and "misses=1" in text and "max_size=5" in text


# --------------------------------------------------------------------------- #
# Decorator contract
# --------------------------------------------------------------------------- #


def test_metadata_is_preserved():
    """The original dropped __name__ and __doc__ -- no functools.wraps."""

    @lru_cache(10)
    def documented(n: int) -> int:
        """Does a thing."""
        return n

    assert documented.__name__ == "documented"
    assert documented.__doc__ == "Does a thing."


def test_cache_clear_resets_everything():
    fn = lru_cache(10)(counting(lambda n: n))
    fn(1), fn(1)
    fn.cache_clear()
    assert fn.cache_info.hits == 0
    assert fn.cache_info.misses == 0
    assert fn.cache_keys() == []
    fn(1)
    assert fn.__wrapped__.calls == 2


def test_two_decorated_functions_do_not_share_a_cache():
    a = lru_cache(10)(counting(lambda n: n))
    b = lru_cache(10)(counting(lambda n: n * 2))
    assert a(5) == 5
    assert b(5) == 10


def test_exceptions_are_not_cached():
    """A failed call must be retried, not memoised as a failure."""
    state = {"fail": True}

    @lru_cache(10)
    def flaky(n):
        if state["fail"]:
            raise ValueError("boom")
        return n

    with pytest.raises(ValueError):
        flaky(1)
    state["fail"] = False
    assert flaky(1) == 1


def test_recursion_works():
    @lru_cache(None)
    def fib(n: int) -> int:
        return n if n < 2 else fib(n - 1) + fib(n - 2)

    assert fib(60) == 1548008755920


# --------------------------------------------------------------------------- #
# Concurrency
# --------------------------------------------------------------------------- #


def test_counters_stay_consistent_under_threads():
    fn = lru_cache(64)(lambda n: n * 2)

    def hammer():
        for i in range(400):
            fn(i % 32)

    threads = [threading.Thread(target=hammer) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    info = fn.cache_info
    assert info.hits + info.misses == 8 * 400
    assert info.cur_size <= 64
