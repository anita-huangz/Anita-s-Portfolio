"""W-TinyLFU: the admission filter, the sketch, and what they buy.

The behavioural tests matter more than the hit-rate ones here. A hit rate is a
property of a workload and moves with the machine's random seed; "a key the
cache has never held still has a frequency" is a property of the design, and it
is the property everything else rests on.
"""

import pytest

from fastcache import cached
from fastcache.policy import LFUPolicy, TinyLFUPolicy, make_policy
from fastcache.sketch import MAX_COUNT, CountMinSketch


class TestSketch:
    def test_counts_what_it_has_seen(self):
        s = CountMinSketch(64)
        for _ in range(5):
            s.increment("a")
        s.increment("b")
        assert s.estimate("a") == 5
        assert s.estimate("b") == 1
        assert s.estimate("never seen") == 0

    def test_never_underestimates_between_halvings(self):
        """Collisions can only inflate a count. That direction is the safe one.

        An overestimate keeps a cold key around; an underestimate would evict a
        hot one, which is the mistake that actually costs a fetch. The property
        holds *within an epoch* -- aging is the one thing that lowers a count,
        deliberately, so the sketch is sized here to avoid halving mid-test.
        """
        s = CountMinSketch(4000)
        truth: dict[str, int] = {}
        for i in range(4000):
            key = f"k{i % 700}"
            s.increment(key)
            truth[key] = truth.get(key, 0) + 1
        assert s.halvings == 0, "this test is about collisions, not aging"
        for key, exact in truth.items():
            assert s.estimate(key) >= min(exact, MAX_COUNT)

    def test_aging_is_the_one_thing_that_lowers_a_count(self):
        """And it is a feature: it is how a stale hot set loses its grip."""
        s = CountMinSketch(16)
        for _ in range(MAX_COUNT):
            s.increment("yesterdays champion")
        assert s.estimate("yesterdays champion") == MAX_COUNT
        for i in range(1000):
            s.increment(f"todays traffic {i}")
        assert s.halvings > 0
        assert s.estimate("yesterdays champion") < MAX_COUNT

    def test_counters_saturate_rather_than_wrap(self):
        s = CountMinSketch(16)
        for _ in range(500):
            s.increment("hot")
        assert s.estimate("hot") == MAX_COUNT

    def test_halving_is_the_aging_step(self):
        s = CountMinSketch(16)
        for _ in range(8):
            s.increment("a")
        s.halve()
        assert s.estimate("a") == 4
        s.halve()
        assert s.estimate("a") == 2

    def test_halving_does_not_leak_between_packed_counters(self):
        """Two counters share a byte; a careless shift moves a bit across."""
        s = CountMinSketch(64)
        for _ in range(MAX_COUNT):
            s.increment("x")
        before = {i: s._get(i) for i in range(s.width * s.depth)}
        s.halve()
        for i, value in before.items():
            assert s._get(i) == value >> 1

    def test_aging_happens_on_its_own(self):
        s = CountMinSketch(8)  # sample_size = 80
        for i in range(400):
            s.increment(f"k{i}")
        assert s.halvings > 0

    def test_memory_is_fixed_regardless_of_key_count(self):
        s = CountMinSketch(100)
        size = s.bytes_used
        for i in range(100_000):
            s.increment(f"k{i}")
        assert s.bytes_used == size

    def test_capacity_must_be_positive(self):
        with pytest.raises(ValueError):
            CountMinSketch(0)


class TestAdmission:
    def test_a_new_key_is_always_admitted_to_the_window(self):
        """The bug in plain LFU: a fresh key could never get in at all."""
        policy = make_policy("tinylfu", 100)
        for i in range(50):
            policy.insert(i)
            for _ in range(20):
                policy.touch(i)
        policy.insert("newcomer")
        assert policy.segments["window"] >= 1

    def test_lfu_by_contrast_evicts_the_newcomer_immediately(self):
        """The behaviour TinyLFU exists to fix, pinned so the contrast is real."""
        lfu = LFUPolicy()
        for i in range(10):
            lfu.insert(i)
            for _ in range(5):
                lfu.touch(i)
        lfu.insert("newcomer")
        assert lfu.evict() == "newcomer"

    def test_frequency_survives_eviction(self):
        """The whole reason for a sketch rather than counts beside the entries."""
        policy = make_policy("tinylfu", 4)
        for _ in range(6):
            policy.insert("rare-but-repeated")
            policy.discard("rare-but-repeated")
        assert policy.frequency("rare-but-repeated") >= 6

    def test_a_frequent_candidate_displaces_a_rare_resident(self):
        policy = make_policy("tinylfu", 10)
        for i in range(10):
            policy.insert(i)
        # Make one key clearly popular before it is ever admitted.
        for _ in range(12):
            policy.frequency(0)
            policy._sketch.increment("popular")
        policy.insert("popular")
        evicted = [policy.evict() for _ in range(3)]
        assert "popular" not in evicted

    def test_promotion_moves_a_hit_key_out_of_probation(self):
        # Driven the way the cache drives it: evict only when over capacity.
        # Inserting and evicting in lockstep keeps the cache empty and nothing
        # ever reaches probation at all.
        policy = make_policy("tinylfu", 20)
        held: set[int] = set()
        for i in range(60):
            policy.insert(i)
            held.add(i)
            while len(held) > 20:
                held.discard(policy.evict())
        probation_before = policy.segments["probation"]
        assert probation_before > 0
        for key in list(policy._probation)[:3]:
            policy.touch(key)
        assert policy.segments["protected"] >= 1
        assert policy.segments["probation"] < probation_before


class TestPolicyContract:
    """Whatever it does internally, it has to behave like a policy."""

    def test_evicting_an_empty_policy_raises(self):
        with pytest.raises(KeyError):
            make_policy("tinylfu", 10).evict()

    def test_discard_is_idempotent_and_silent(self):
        policy = make_policy("tinylfu", 10)
        policy.insert("a")
        policy.discard("a")
        policy.discard("a")
        policy.discard("never inserted")

    def test_clear_empties_every_segment(self):
        policy = make_policy("tinylfu", 10)
        for i in range(30):
            policy.insert(i)
        policy.clear()
        assert policy.segments == {"window": 0, "probation": 0, "protected": 0}
        assert policy.frequency(0) == 0

    def test_evict_always_names_a_key_it_holds(self):
        policy = make_policy("tinylfu", 16)
        held = set()
        for i in range(200):
            policy.insert(i)
            held.add(i)
            while len(held) > 16:
                victim = policy.evict()
                assert victim in held, "named a key it was not holding"
                held.discard(victim)
        assert len(held) == 16

    def test_window_fraction_is_validated(self):
        for bad in (0, 1, -0.5, 2.0):
            with pytest.raises(ValueError):
                TinyLFUPolicy(100, window_fraction=bad)


class TestThroughTheCache:
    def test_it_works_as_a_cache_policy(self):
        calls = []

        @cached(max_size=32, policy="tinylfu")
        def double(n):
            calls.append(n)
            return n * 2

        for _ in range(3):
            for i in range(10):
                assert double(i) == i * 2
        assert len(calls) == 10, "a stable working set should not be evicted"
        assert double.cache_info.hit_rate > 0.6

    def test_it_never_exceeds_max_size(self):
        @cached(max_size=25, policy="tinylfu")
        def identity(n):
            return n

        for i in range(500):
            identity(i % 300)
        assert identity.cache_info.cur_size <= 25

    def test_it_is_selectable_by_name(self):
        assert make_policy("tinylfu", 10).name == "tinylfu"
        with pytest.raises(ValueError, match="unknown policy"):
            make_policy("nonesuch", 10)
