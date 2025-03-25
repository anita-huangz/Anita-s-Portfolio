class CacheInfo:
    """
    CacheInfo object used to represent the current status of `lru_cache`

    - hits: number of calls where the result was returned from the cache
    - misses: number of calls where the result needed to be calculated by calling the function
    - max_size: the maximum number of entries the cache can store
    - cur_size: the number of entries currently stored
    """

    def __init__(self, max_size):
        self.max_size = max_size
        self.misses = 0
        self.hits = 0
        self.cur_size = 0

    def __repr__(self):
        return f"CacheInfo(hits={self.hits}, misses={self.misses}, max_size={self.max_size}, cur_size={self.cur_size})"


def lru_cache(max_size = 128):
    """
    A decorator that maintains an LRU cache that stores max_size arguments and their results
    - max_size: Maximum number of entries the cache can store
    """

    def cache(func):
        # Inner cache dict and keys list for LRU tracking
        inner_cache = {}
        keys = []
        cache_info = CacheInfo(max_size)

        def wrapped_function(*args, **kwargs):
            # Create a unique key from args and kwargs
            typed_args = tuple((type(arg), arg) for arg in args)
            typed_kwargs = tuple(sorted((k, (type(v), v)) for k, v in kwargs.items()))
            key = (typed_args, typed_kwargs)

            # Check if the result is not in the cache (Cache miss)
            if key not in inner_cache:
                cache_info.misses += 1
                keys.append(key)
                inner_cache[key] = func(*args, **kwargs)
                cache_info.cur_size += 1

                if len(inner_cache) > max_size:
                    # Remove the least recently used item
                    del inner_cache[keys[0]]
                    keys.pop(0)
                    cache_info.cur_size -= 1
                return inner_cache[key]

            # If the result is in the cache (Cache hit)
            keys.remove(key)
            keys.append(key)
            cache_info.hits += 1
            return inner_cache[key]

        wrapped_function.cache_info = cache_info
        return wrapped_function

    return cache
