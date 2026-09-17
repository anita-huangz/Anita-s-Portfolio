"""An O(1) LRU cache decorator."""

from .lru import CacheInfo, Unhashable, lru_cache, make_key

__all__ = ["CacheInfo", "Unhashable", "lru_cache", "make_key"]

__version__ = "0.2.0"
