"""Measure the cache against the standard library and against no cache at all.

The interesting number is the *hit* path. A cache that is slow to answer a hit
is not a cache; it is a slower version of the function plus a dictionary.
"""

from __future__ import annotations

import argparse
import functools
import time
from collections.abc import Callable

from .lru import lru_cache


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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Benchmark the LRU cache.")
    parser.add_argument("--calls", type=int, default=20_000)
    parser.add_argument("--repeats", type=int, default=5)
    parser.add_argument(
        "--sizes",
        default="8,128,1024",
        help="Cache sizes to sweep. The gap grows with size for an O(n) hit path.",
    )
    args = parser.parse_args(argv)

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
