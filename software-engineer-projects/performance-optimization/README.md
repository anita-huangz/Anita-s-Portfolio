# Custom lru_cache Decorator 

## Overview
This project implements a custom version of Python’s built-in functools.lru_cache decorator. It is designed to improve computational efficiency by caching function call results and applying a Least Recently Used (LRU) cache eviction policy.

By storing results of previous calls, the decorator avoids redundant computation, optimizing both performance and memory usage.

## Features
1. LRU Cache Mechanism
- Caches up to max_size recent function calls.
- Evicts the least recently used entry once capacity is exceeded.
2. Customizable Cache Size
- Default max_size is 128, but it can be customized.
3. Function Call Tracking
- Tracks hits, misses, current size, and maximum size through a CacheInfo object.
4. Type-Aware Caching
- Differentiates between f(3) and f(3.0) (important distinction in Python).
5. Testable & Introspectable
- The wrapped function includes a .cache_info attribute for inspection and testing.

##  Performance & Optimization
This custom decorator improves runtime performance by:
- Avoiding redundant computations via result caching.
- Managing memory use with bounded cache size and LRU eviction.
- Allowing introspection for debugging and tuning cache behavior.

## Use Cases
- Recursive or computationally expensive functions
- API/data-fetching logic with repeated calls
- Any function where repeated input → same output
