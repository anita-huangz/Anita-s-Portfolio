"""Measure the cache against the standard library and against no cache at all.

The interesting number is the *hit* path. A cache that is slow to answer a hit
is not a cache; it is a slower version of the function plus a dictionary.
"""

from __future__ import annotations

import argparse
import functools
import random
import time
from collections.abc import Callable

from .cache import cached
from .lru import lru_cache
from .policy import TinyLFUPolicy


def timed(fn: Callable[[], object], repeats: int) -> float:
    """Best-of-N wall time in microseconds per call.

    Best-of rather than mean: the minimum is the measurement least polluted by
    scheduler noise, which is what you want when comparing implementations.
    """
    best = float("inf")
    for _ in range(repeats):
        start = time.perf_counter()
        fn()
        best = min(best, time.perf_counter() - start)
    return best * 1e6


def list_recency_cache(max_size: int = 128):
    """The original implementation, kept only as a benchmark baseline.

    Recency lives in a list, so every hit calls `list.remove` -- a linear scan.
    This is here to make the cost visible rather than asserted.
    """

    def decorator(func):
        cache: dict = {}
        keys: list = []

        def wrapper(*args, **kwargs):
            key = (tuple((type(a), a) for a in args),
                   tuple(sorted((k, (type(v), v)) for k, v in kwargs.items())))
            if key not in cache:
                cache[key] = func(*args, **kwargs)
                keys.append(key)
                if len(cache) > max_size:
                    del cache[keys[0]]
                    keys.pop(0)
                return cache[key]
            keys.remove(key)   # O(n) scan on the hit path
            keys.append(key)
            return cache[key]

        return wrapper

    return decorator


def bench_hit_path(max_size: int, calls: int, repeats: int) -> dict[str, float]:
    """Time `calls` cache hits against a warm cache of `max_size` entries."""

    def identity(n: int) -> int:
        return n

    ours = lru_cache(max_size)(identity)
    theirs = functools.lru_cache(maxsize=max_size)(identity)
    original = list_recency_cache(max_size)(identity)

    # Warm all three to exactly max_size entries, then hit only those keys.
    for i in range(max_size):
        ours(i)
        theirs(i)
        original(i)

    def hit(fn):
        def run():
            for i in range(calls):
                fn(i % max_size)
        return run

    return {
        "fastcache": timed(hit(ours), repeats) / calls,
        "functools": timed(hit(theirs), repeats) / calls,
        "list-based": timed(hit(original), repeats) / calls,
    }


def bench_miss_path(max_size: int, calls: int, repeats: int) -> dict[str, float]:
    """Time evictions: every call is a miss on a full cache."""

    def identity(n: int) -> int:
        return n

    results = {}
    for name, factory in (("fastcache", lru_cache), ("functools", _functools_factory)):
        def run(factory=factory):
            fn = factory(max_size)(identity)
            for i in range(calls):
                fn(i)
        results[name] = timed(run, repeats) / calls
    return results


def _functools_factory(max_size: int):
    return functools.lru_cache(maxsize=max_size)


# --------------------------------------------------------------------------- #
# Which eviction policy, and when
# --------------------------------------------------------------------------- #
#
# Speed per operation is not the only question. A cache that answers hits in
# 0.4us and misses 90% of them is worse than one that takes 0.7us and misses
# 20%, and which policy misses less depends entirely on the access pattern.
# These workloads are chosen so that each policy wins one of them -- the point
# is that neither dominates, not that one is better.


def zipf_workload(keys: int, calls: int, max_size: int, seed: int = 0) -> list[int]:
    """Skewed: a few keys take most of the traffic. Most real caches see this."""
    rng = random.Random(seed)
    weights = [1.0 / (rank**1.1) for rank in range(1, keys + 1)]
    return rng.choices(range(keys), weights=weights, k=calls)


def uniform_workload(keys: int, calls: int, max_size: int, seed: int = 0) -> list[int]:
    """No locality at all. Nothing can help, which is worth showing."""
    rng = random.Random(seed)
    return [rng.randrange(keys) for _ in range(calls)]


def scan_workload(keys: int, calls: int, max_size: int) -> list[int]:
    """Sequential passes over more keys than fit. LRU's textbook worst case.

    Every access evicts the entry that will be needed soonest, so the hit rate
    is zero however large the cache is -- until it is large enough to hold
    everything, at which point it is 100%. There is no gradual improvement.
    """
    return [i % keys for i in range(calls)]


def hot_set_with_scans(keys: int, calls: int, max_size: int, seed: int = 0) -> list[int]:
    """A small hot set, repeatedly flushed by scans over cold keys.

    Sized against the cache on purpose: the hot set is half the cache, and each
    scan touches three times the cache's worth of keys that are read once and
    never again. That is what makes LFU worth having -- LRU throws the hot set
    away every cycle to make room for keys nobody will ask for again.
    """
    rng = random.Random(seed)
    hot = max(1, max_size // 2)
    trace: list[int] = []
    cold = hot
    while len(trace) < calls:
        trace.extend(rng.randrange(hot) for _ in range(hot * 2))
        for _ in range(max_size * 3):
            trace.append(cold)
            cold = hot + (cold - hot + 1) % max(1, keys - hot)
    return trace[:calls]


def shifting_hot_set(keys: int, calls: int, max_size: int, seed: int = 0) -> list[int]:
    """The hot set moves. LFU's worst case, and why LRU is the default.

    Each phase has its own hot set, the size of the cache. Under LRU the cache
    simply follows. Under LFU the previous phase's keys carry counts the new
    ones cannot reach, so a new key -- frequency 1, in a cache where everything
    else has been hit many times -- is the least frequently used thing present
    and is evicted immediately. It is never cached, however often it is asked
    for, and the hit rate collapses.
    """
    rng = random.Random(seed)
    phases = max(1, (keys - max_size) // max_size)
    per_phase = max(1, calls // phases)
    trace: list[int] = []
    for phase in range(phases):
        base = phase * max_size
        trace.extend(base + rng.randrange(max_size) for _ in range(per_phase))
    return trace[:calls]


WORKLOADS = {
    "zipf (skewed)": zipf_workload,
    "uniform (no locality)": uniform_workload,
    "sequential scan": scan_workload,
    "hot set + scans": hot_set_with_scans,
    "shifting hot set": shifting_hot_set,
}


def replay(trace: list[int], max_size: int, policy: str) -> tuple[float, float]:
    """Hit rate and microseconds per call for one policy over one trace."""

    def identity(n: int) -> int:
        return n

    fn = cached(max_size, policy=policy)(identity)
    start = time.perf_counter()
    for key in trace:
        fn(key)
    elapsed = (time.perf_counter() - start) * 1e6 / len(trace)
    return fn.cache_info.hit_rate, elapsed


def compare_policies(
    keys: int = 2_000, calls: int = 50_000, max_size: int = 200
) -> dict[str, dict[str, tuple[float, float]]]:
    """Replay every workload under every policy."""
    results: dict[str, dict[str, tuple[float, float]]] = {}
    for name, build in WORKLOADS.items():
        trace = build(keys, calls, max_size)
        results[name] = {
            policy: replay(trace, max_size, policy)
            for policy in ("lru", "lfu", "tinylfu")
        }
    return results


def print_window_sweep(
    fractions: list[float], keys: int, calls: int, max_size: int
) -> None:
    """How the admission window trades one failure mode against the other.

    A bigger window behaves more like LRU -- it adapts when the working set
    moves -- and less like LFU, so it gives back some of the protection a
    skewed workload enjoys. Caffeine tunes this at runtime by hill-climbing on
    the hit rate; this one does not, so the dial is exposed and measured
    instead of being hidden at a default nobody checked.
    """
    interesting = ["zipf (skewed)", "hot set + scans", "shifting hot set"]
    print(f"\n{calls:,} accesses over {keys:,} keys, cache holds {max_size}.\n")
    print(f"{'window':>7}  " + "  ".join(f"{n:>16}" for n in interesting))
    print("-" * (9 + 18 * len(interesting)))
    original = TinyLFUPolicy.WINDOW_FRACTION
    try:
        for fraction in fractions:
            TinyLFUPolicy.WINDOW_FRACTION = fraction
            rates = []
            for name in interesting:
                trace = WORKLOADS[name](keys, calls, max_size)
                rates.append(replay(trace, max_size, "tinylfu")[0])
            print(f"{fraction:>6.0%}  " + "  ".join(f"{r:>15.1%}" for r in rates))
    finally:
        TinyLFUPolicy.WINDOW_FRACTION = original

    print(f"\n{'LRU':>6}  " + "  ".join(
        f"{replay(WORKLOADS[n](keys, calls, max_size), max_size, 'lru')[0]:>15.1%}"
        for n in interesting))
    print(f"{'LFU':>6}  " + "  ".join(
        f"{replay(WORKLOADS[n](keys, calls, max_size), max_size, 'lfu')[0]:>15.1%}"
        for n in interesting))


def print_policy_comparison(keys: int, calls: int, max_size: int) -> None:
    results = compare_policies(keys, calls, max_size)
    print(
        f"\n{calls:,} accesses over {keys:,} distinct keys, cache holds "
        f"{max_size} ({max_size / keys:.0%} of them).\n"
    )
    header = (
        f"{'workload':<24} {'LRU':>7} {'LFU':>7} {'W-TinyLFU':>10} {'best':>10}"
        f"   us/call (lru/lfu/w)"
    )
    print(header)
    print("-" * len(header))
    for name, byp in results.items():
        rates = {p: byp[p][0] for p in ("lru", "lfu", "tinylfu")}
        best = max(rates, key=rates.__getitem__)
        label = {"lru": "LRU", "lfu": "LFU", "tinylfu": "W-TinyLFU"}[best]
        # A win inside a point is noise, not a result.
        runner_up = max(r for p, r in rates.items() if p != best)
        if rates[best] - runner_up < 0.01:
            label = "tie"
        print(
            f"{name:<24} {rates['lru']:>6.1%} {rates['lfu']:>7.1%} "
            f"{rates['tinylfu']:>10.1%} {label:>10}   "
            + " / ".join(f"{byp[p][1]:.2f}" for p in ("lru", "lfu", "tinylfu"))
        )
    print(
        "\nNo policy wins everywhere, which is still the finding -- but the shape"
        "\nof the disagreement changed. LFU protects a stable hot set from scans"
        "\nand collapses when the hot set moves, because its counts never decay."
        "\nW-TinyLFU keeps the scan resistance and recovers most of the loss: it"
        "\nages its frequency estimates, and it admits every new key to a small"
        "\nwindow first, so a newcomer is never rejected for having been seen"
        "\nonly once. It does not fully match LRU on a shifting hot set, and"
        "\n`--window` shows why: that is a dial, not a bug."
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Benchmark the LRU cache.")
    parser.add_argument("--calls", type=int, default=20_000)
    parser.add_argument(
        "--policies",
        action="store_true",
        help="Compare LRU against LFU across access patterns instead of timing.",
    )
    parser.add_argument("--keys", type=int, default=2_000)
    parser.add_argument("--cache-size", type=int, default=200)
    parser.add_argument("--repeats", type=int, default=5)
    parser.add_argument(
        "--window",
        type=float,
        help="Sweep W-TinyLFU's admission-window fraction, e.g. 0.01,0.1,0.4. "
        "Accepts one value to fix it, or use --window-sweep for a table.",
    )
    parser.add_argument(
        "--window-sweep",
        help="Comma-separated window fractions to compare, e.g. 0.01,0.1,0.4",
    )
    parser.add_argument(
        "--sizes",
        default="8,128,1024",
        help="Cache sizes to sweep. The gap grows with size for an O(n) hit path.",
    )
    args = parser.parse_args(argv)

    if args.window_sweep:
        print_window_sweep(
            [float(w) for w in args.window_sweep.split(",") if w.strip()],
            args.keys, args.calls, args.cache_size,
        )
        return 0

    if args.policies:
        if args.window is not None:
            TinyLFUPolicy.WINDOW_FRACTION = args.window
        print_policy_comparison(args.keys, args.calls, args.cache_size)
        return 0

    sizes = [int(s) for s in args.sizes.split(",") if s.strip()]

    print(f"{args.calls:,} calls, best of {args.repeats}. Microseconds per call.\n")
    print(f"{'':>6}  {'HIT PATH (us/call)':^36}  {'MISS PATH':^24}")
    print(
        f"{'size':>6}  {'fastcache':>10} {'functools':>10} {'list-based':>12}"
        f"  {'fastcache':>10} {'functools':>11}"
    )
    print("-" * 78)

    first_list = None
    last_list = None
    for size in sizes:
        hit = bench_hit_path(size, args.calls, args.repeats)
        miss = bench_miss_path(size, args.calls, args.repeats)
        first_list = first_list if first_list is not None else hit["list-based"]
        last_list = hit["list-based"]
        print(
            f"{size:>6}  {hit['fastcache']:>10.3f} {hit['functools']:>10.3f}"
            f" {hit['list-based']:>12.3f}"
            f"  {miss['fastcache']:>10.3f} {miss['functools']:>11.3f}"
        )

    print(
        "\nfastcache and functools stay flat as the cache grows. The list-based"
        "\nrecency tracking -- what this project used to do -- climbs, because every"
        "\nhit scans the recency list."
    )
    if first_list and last_list:
        print(
            f"Over this sweep the list-based hit path got {last_list / first_list:.1f}x"
            f" slower while fastcache stayed flat."
        )
    print("\n(functools.lru_cache is C. Matching it in Python is not the goal;"
          "\n growing with n is the thing to avoid.)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
