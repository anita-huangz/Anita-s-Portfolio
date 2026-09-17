# fastcache — an O(1) LRU cache

An LRU cache decorator in pure Python, with a benchmark harness that measures
it against `functools.lru_cache` and against the list-based approach this
project used to use.

```python
from fastcache import lru_cache

@lru_cache(max_size=128)
def expensive(n: int) -> int:
    ...

expensive.cache_info     # CacheInfo(hits=42, misses=7, max_size=128, cur_size=7)
expensive.cache_clear()
expensive.cache_keys()   # LRU order, oldest first
```

## Run it

```bash
python3 -m venv .venv && .venv/bin/pip install -e ".[dev]"
pytest -q                                      # 24 tests
fastcache-bench --sizes 128,1024,8192,32768
```

## The bug: the hit path was O(n)

The original tracked recency in a list:

```python
keys.remove(key)     # linear scan, on every cache hit
keys.append(key)
```

`list.remove` scans until it finds the element. So the *hit* path — the path
the cache exists to make fast — did O(n) work in the size of the cache to
answer a question the dict had already answered in O(1). A 128-entry cache did
a 128-element scan per hit.

This version keeps recency in the dict itself. Python dicts have preserved
insertion order since 3.7, so "move to most-recently-used" is `pop` then
reinsert — both O(1) — and the least-recently-used entry is just
`next(iter(cache))`.

`fastcache-bench` runs all three side by side. Microseconds per call, 20,000
calls, best of 5:

```
  size   fastcache  functools   list-based   fastcache   functools
------------------------------------------------------------------------------
   128       0.424      0.032        0.534       0.674       0.061
  1024       0.451      0.043        0.615       0.843       0.068
  8192       0.457      0.044        1.187       1.182       0.068
 32768       0.462      0.043        4.556       0.653       0.072
```

Across that sweep the list-based hit path got **8.5× slower** while fastcache
stayed flat — 0.42µs to 0.46µs. That flatness is the entire claim; the absolute
numbers are secondary.

`functools.lru_cache` is ~10× faster than both because it's C. Matching it in
pure Python isn't the goal and isn't achievable. Growing with *n* is the thing
to avoid, and only one of these three does.

## Other fixes

**Metadata was dropped.** No `functools.wraps`, so a decorated function lost
its `__name__`, `__doc__`, and signature — which breaks `help()`, tracebacks,
and anything that introspects.

**`1`, `1.0`, and `True` shared a cache entry.** They're all `==` in Python, so
a function branching on type returned the first caller's answer to everyone.
The key now folds in `type(arg)`.

**`f(1, 2)` and `f(1, b=2)` could collide.** Positional and keyword sections of
the key are now separated by a sentinel.

**Unhashable arguments raised a bare `TypeError`** from deep inside the
decorator. They now raise `Unhashable` naming the function and the reason.

**No `cache_clear`.** There was no way to reset a cache, which makes the
decorator awkward to use in tests.

**Not thread-safe.** Concurrent calls could interleave between the dict read
and the counter update, corrupting both. A lock now guards cache and counter
mutations — but the wrapped function is called *outside* the lock, so one slow
call doesn't block every other reader.

## Semantics

- **Exceptions aren't cached.** A failed call is retried next time rather than
  memoised as a permanent failure.
- **`max_size=None`** caches without bound; **`max_size=0`** disables caching
  while still counting misses. Both match `functools.lru_cache`.
- **Eviction is strict LRU**: reading an entry protects it from the next
  eviction, which is the property the list version got right and paid for.

## Limits

- Keys hold references to their arguments, so a cached entry keeps those
  objects alive. Unbounded caches on large objects will grow memory.
- The lock is a single mutex, not per-shard. Under heavy multi-threaded load on
  a fast function, lock contention will dominate.
- `cache_keys()` returns internal key tuples; it's for tests and
  introspection, not a public data format.
