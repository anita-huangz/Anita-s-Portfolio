from lru import lru_cache
import time

# Basic arithmetic example
@lru_cache(max_size=5)
def add(a, b):
    print(f"Computing add({a}, {b})")
    return a + b

# Recursive function with exponential benefit
@lru_cache(max_size=100)
def fibonacci(n):
    if n <= 1:
        return n
    return fibonacci(n - 1) + fibonacci(n - 2)

# Simulated expensive function
@lru_cache(max_size=3)
def slow_multiply(a, b):
    print(f"Computing slow_multiply({a}, {b})...")
    time.sleep(1)  # Simulate heavy computation
    return a * b

# Function with keyword arguments
@lru_cache(max_size=5)
def greet(name="User", punctuation="."):
    print(f"Greeting {name}")
    return f"Hello, {name}{punctuation}"

# Function distinguishing argument types
@lru_cache(max_size=5)
def describe_type(x):
    return f"{x} is of type {type(x)}"

# LRU eviction test
@lru_cache(max_size=2)
def square(n):
    print(f"Computing square({n})")
    return n * n


if __name__ == "__main__":
    print("=== Basic Arithmetic ===")
    add(1, 2)  # Miss
    add(2, 1)  # Miss
    add(1, 2)  # Hit
    print(add.cache_info, "\n")

    print("=== Fibonacci ===")
    print(f"Fibonacci(10): {fibonacci(10)}")
    print(fibonacci.cache_info, "\n")

    print("=== Slow Multiply ===")
    slow_multiply(2, 3)  # Miss (sleeps)
    slow_multiply(2, 3)  # Hit (instant)
    print(slow_multiply.cache_info, "\n")

    print("=== Greeting ===")
    greet(name="Alice", punctuation="!")
    greet(name="Alice", punctuation="!")
    print(greet.cache_info, "\n")

    print("=== Type-Aware Caching ===")
    describe_type(3)
    describe_type(3.0)
    describe_type(3)
    print(describe_type.cache_info, "\n")

    print("=== LRU Eviction Demo ===")
    square(1)  # Miss
    square(2)  # Miss
    square(1)  # Hit
    square(3)  # Miss (evicts 2)
    square(2)  # Miss again
    print(square.cache_info)
