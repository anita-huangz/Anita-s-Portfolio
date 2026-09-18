"""Caching with O(1) eviction: a specialised LRU, and a general decorator."""

from .cache import CacheInfo, Unhashable, cached, make_key
from .lru import lru_cache
from .policy import LFUPolicy, LRUPolicy, Policy, make_policy

__all__ = [
    "CacheInfo",
    "LFUPolicy",
    "LRUPolicy",
    "Policy",
    "Unhashable",
    "cached",
    "lru_cache",
    "make_key",
    "make_policy",
]

__version__ = "0.3.0"
