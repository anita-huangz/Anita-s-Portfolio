# fastcache — caching with O(1) eviction

Cache decorators in pure Python, with a benchmark harness that measures them
against `functools.lru_cache`, against the list-based approach this project
used to use, and against each other across access patterns.

```python
from fastcache import lru_cache

@lru_cache(max_size=128)
def expensive(n: int) -> int:
    ...

expensive.cache_info     # CacheInfo(hits=42, misses=7, max_size=128, cur_size=7)
expensive.cache_clear()
expensive.cache_keys()   # LRU order, oldest first
```

For expiry or a different eviction policy, use `cached`:

```python
from fastcache import cached

@cached(max_size=1_000, ttl=60)              # recompute after a minute
def exchange_rate(pair: str) -> float:
    ...

@cached(max_size=1_000, policy="lfu")        # frequency, not recency
def render(template: str) -> str:
    ...

exchange_rate.cache_invalidate("USDGBP")     # you know it changed
exchange_rate.cache_purge()                  # drop dead entries
exchange_rate.cache_info
# CacheInfo(hits=0, misses=1, max_size=1000, cur_size=1, policy='lru',
#           evictions=0, ttl=60, expirations=0)
```

## Run it

```bash
python3 -m venv .venv && .venv/bin/pip install -e ".[dev]"
pytest -q                                      # 98 tests
fastcache-bench --sizes 128,1024,8192,32768    # timing
fastcache-bench --policies                     # LRU vs LFU by workload
```

## Expiry: "computed" is not the same as "still true"

`lru_cache` answers *has this been computed?* A service needs *has this been
computed recently enough?* An exchange rate, a feature flag, or a row count is
not wrong to cache — it is wrong to cache forever, and without a TTL the only
options were serving a stale answer or not caching at all.

Three things here are easy to get subtly wrong, and all three are tested:

**An expired entry must not count as a hit.** Checking freshness after
incrementing `hits` inflates the hit rate with entries that were thrown away —
and hit rate is the number people use to decide whether the cache is working.
Expiries are counted separately, so a low hit rate caused by a short TTL looks
different from one caused by a cold workload.

**An expired entry still occupies capacity.** It is dropped when read, but
nothing reads a key that has gone cold — so a cache can be nominally full of
entries that are all dead and evict a live one to make room. Eviction takes a
dead entry first, and `cache_purge()` reclaims the rest.

**Finding the dead entry has to be O(1).** Scanning for an expired key on
eviction would reintroduce the exact O(n) hit path this project exists to
document, on a cache that is full and therefore hot. It doesn't need a heap:
every entry gets `clock() + ttl` with the same `ttl`, so **deadline order is
insertion order** and the front of the deadline dict is always the next to die.

The clock is `time.monotonic`, not `time.time`. Wall-clock time jumps backwards
when NTP corrects it, which would leave entries alive past their TTL or expire
a whole cache at once. It's injectable, so the TTL tests advance time instead
of sleeping.

## Which eviction policy? Measured, not assumed

The project shipped one policy and no evidence it was the right one. LFU is now
available, implemented in O(1) — frequency buckets plus a tracked minimum, so
eviction never scans for the least-used key.

50,000 accesses over 2,000 distinct keys, cache holds 200 (10% of them):

| workload | LRU hit | LFU hit | winner |
|---|---:|---:|---|
| zipf (skewed) | 71.3% | 76.4% | LFU +5 pts |
| uniform (no locality) | 10.1% | 10.1% | tie |
| sequential scan | 0.0% | 0.0% | tie |
| hot set + scans | 14.3% | 24.9% | **LFU +11 pts** |
| shifting hot set | 96.4% | 10.7% | **LRU +86 pts** |

**Neither policy wins everywhere, and that is the finding.**

LFU's case is the fourth row: a stable hot set, repeatedly flushed by scans
over keys that are read once and never again. LRU throws the hot set away every
cycle to make room for them; LFU keeps it, and 24.9% is essentially the
theoretical maximum for that trace.

LRU's case is the fifth row, and it is not close. When the hot set moves, the
previous phase's keys carry frequency counts the new ones cannot reach — so a
new key, frequency 1 in a cache where everything else has been hit many times,
is the least frequently used thing present and is evicted **immediately**. It
is never cached at all, however often it is asked for. LFU has no decay, so
this is permanent, and there is a test asserting exactly this behaviour rather
than papering over it.

Rows 2 and 3 are worth keeping in the table for the opposite reason: no policy
helps. With no locality, nothing can; and a scan over more keys than fit gives
0% at any cache size until the cache holds everything, with no gradual
improvement in between.

**If you don't know the workload, use LRU.** Its bad case is a scan, and its
bad case is temporary.

## Fixing LFU's collapse: W-TinyLFU

The table above has a hole in it. LFU loses to LRU by 86 points on a shifting
hot set, and the reason is structural rather than a tuning problem:

**Counts never decay.** A key that was hot an hour ago holds a frequency
nothing new can reach, so the cache stays frozen around a working set that has
moved on.

**A new key cannot get in.** A fresh key has frequency 1. If everything
resident has been touched more, it is by definition the least frequently used
and goes straight back out — however often it is asked for afterwards.

`policy="tinylfu"` fixes both, following Caffeine's design. Every new key is
admitted unconditionally to a small LRU **window**; only when pushed out of the
window must it beat the main region's victim on estimated frequency. Those
estimates live in a **count-min sketch** that halves all its counters
periodically, so history decays instead of accumulating forever.

```
$ fastcache-bench --policies --calls 50000

workload                     LRU     LFU  W-TinyLFU       best   us/call (lru/lfu/w)
------------------------------------------------------------------------------------
zipf (skewed)             71.3%   76.4%      77.7%  W-TinyLFU   0.66 / 0.94 / 2.75
uniform (no locality)     10.1%   10.1%      10.0%        tie   0.94 / 1.12 / 5.14
sequential scan            0.0%    0.0%       0.0%        tie   0.94 / 1.03 / 5.40
hot set + scans           14.3%   24.9%      24.8%        tie   0.93 / 0.94 / 4.59
shifting hot set          96.4%   10.7%      71.8%        LRU   0.55 / 1.17 / 3.08
```

**The collapse is mostly gone: 10.7% → 71.8%.** Scan resistance is kept
(24.8% against LFU's 24.9%), and on the skewed workload it beats both — the
admission filter keeps one-hit wonders from displacing the genuinely popular.

It does **not** reach LRU's 96.4%, and the reason is a deliberate dial rather
than a defect:

```
$ fastcache-bench --window-sweep 0.01,0.1,0.4,0.6 --calls 50000

 window     zipf (skewed)   hot set + scans  shifting hot set
---------------------------------------------------------------
    1%            77.7%            25.9%            71.8%
   10%            77.4%            25.5%            73.5%
   40%            75.9%            24.7%            81.1%
   60%            74.5%            22.9%            86.0%

   LRU            71.3%            14.3%            96.4%
   LFU            76.4%            24.9%            10.7%
```

A wider window behaves more like LRU and adapts faster; a narrower one behaves
more like LFU and protects the skewed case better. There is no setting that
wins both columns. Caffeine resolves this by hill-climbing the window size at
runtime against the observed hit rate; this implementation does not, so the
dial is exposed and measured rather than buried at a default nobody checked.

### What it costs

**Three to five times the CPU per call.** Every access hashes the key into four
sketch positions and maintains three segments, and on the two workloads with no
locality to exploit — uniform and scan — that buys exactly nothing. On a fast
function with a low hit rate, W-TinyLFU is strictly the wrong choice, and the
`us/call` column says so rather than leaving it to be discovered.

**Memory is bounded and does not grow with the key space**, which is the whole
reason the frequency estimates live in a sketch rather than a dictionary of
counts: 4 KB at capacity 200, 256 KB at capacity 10,000, unchanged whether the
workload touches a thousand distinct keys or ten million. Counters are four
bits, packed two to a byte, saturating at 15 — enough to rank keys, which is
the only question being asked.

**The estimates are approximate, and only ever too high.** Hash collisions add
counts, never remove them, so a key that looks rare really is rare. That is the
direction that matters: overestimating keeps a cold key one extra round, while
underestimating would evict a hot one and cost a real fetch.

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
- **`lru_cache` is strict LRU**: reading an entry protects it from the next
  eviction, which is the property the list version got right and paid for.
- **`cached(policy="lfu")` may decline to admit a key.** A fresh key has
  frequency 1; if every entry has been hit more, the new key is the least
  frequently used thing in the cache and goes straight back out. The call still
  returns the right answer — it just isn't retained.
- **`lru_cache` and `cached(policy="lru")` are separate implementations on
  purpose.** Generality costs one method call per hit, measured at 0.43 → 0.54
  µs (25%). Both are flat in the cache size, which is the property that matters, but
  if you want LRU and nothing else the specialised one is faster. Everything
  shared — `make_key`, `CacheInfo` — is defined once, in `cache.py`, because
  two copies of the key function would be two chances to key a call
  differently and the bug would look like a cache miss.

## Limits

- Keys hold references to their arguments, so a cached entry keeps those
  objects alive. Unbounded caches on large objects will grow memory.
- The lock is a single mutex, not per-shard. Under heavy multi-threaded load on
  a fast function, lock contention will dominate.
- `cache_keys()` returns internal key tuples; it's for tests and
  introspection, not a public data format.
- **`policy="lfu"` still has no aging**, and keeps its collapse. It is left
  that way on purpose: it is the baseline `policy="tinylfu"` is measured
  against, and deleting it would delete the evidence. Use `tinylfu` unless you
  want the unaged behaviour specifically.
- **W-TinyLFU's window is fixed, not adaptive.** Caffeine hill-climbs it at
  runtime against the observed hit rate. Here it is a constructor argument with
  a measured sweep, which is honest but is not the same thing — no single
  setting wins every workload.
- **TTL is per-decorator, not per-entry.** One lifetime for every key is what
  makes the O(1) expiry queue work; a per-call TTL would need a real heap.
- **Two threads can compute the same key concurrently.** The function runs
  outside the lock so a slow call doesn't block every reader, which means no
  single-flight guarantee. The first value stored wins and both callers get a
  consistent answer.
