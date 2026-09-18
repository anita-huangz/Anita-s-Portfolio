"""Is the trie worth it, or would a dict have done?

A trie is more code than a dictionary and it is lossy -- the fixed 27-symbol
alphabet folds case and punctuation away. That trade only pays if prefix and
wildcard lookup are genuinely cheaper than scanning, so this measures it rather
than assuming it.

The number to read is not the speedup ratio, which moves around with how many
words happen to match. It is the shape of the two columns: a scan visits every
key, so its cost grows with the vocabulary, while the trie walks to the prefix
and then only over the answers.

    python -m trie_search.benchmark
"""

from __future__ import annotations

import argparse
import random
import re
import string
import time
from collections.abc import Callable

from .trie import Trie

#: Fixed so the table is reproducible between runs and machines.
SEED = 0


def vocabulary(count: int, seed: int = SEED) -> list[str]:
    """`count` distinct lowercase words of 3 to 10 letters."""
    rng = random.Random(seed)
    out: set[str] = set()
    while len(out) < count:
        length = rng.randint(3, 10)
        out.add("".join(rng.choice(string.ascii_lowercase) for _ in range(length)))
    return sorted(out)


def best_of(fn: Callable[[], int], repeats: int = 5) -> tuple[float, int]:
    """Fastest of `repeats` runs, in milliseconds, plus the result count.

    Fastest rather than mean: the slow runs are the machine doing something
    else, and the question here is how much work the algorithm does.
    """
    best = float("inf")
    count = 0
    for _ in range(repeats):
        started = time.perf_counter()
        count = fn()
        best = min(best, time.perf_counter() - started)
    return best * 1000, count


def compare(size: int, prefix: str, pattern: str, repeats: int = 5) -> dict[str, float]:
    """One row: trie against a plain dict, for prefix and wildcard lookup."""
    keys = vocabulary(size)
    trie = Trie({key: index for index, key in enumerate(keys)})
    plain = {key: index for index, key in enumerate(keys)}
    # `?` is a single character, which is `.` to the regex engine.
    regex = re.compile("^" + pattern.replace("?", ".") + "$")

    prefix_trie, matches = best_of(
        lambda: len(list(trie.keys_with_prefix(prefix))), repeats
    )
    prefix_scan, _ = best_of(
        lambda: sum(1 for key in plain if key.startswith(prefix)), repeats
    )
    wild_trie, wild_matches = best_of(
        lambda: len(list(trie.wildcard_search(pattern))), repeats
    )
    wild_scan, _ = best_of(lambda: sum(1 for key in plain if regex.match(key)), repeats)

    return {
        "size": size,
        "prefix_trie": prefix_trie,
        "prefix_scan": prefix_scan,
        "prefix_matches": matches,
        "wild_trie": wild_trie,
        "wild_scan": wild_scan,
        "wild_matches": wild_matches,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Trie against a dictionary scan.")
    parser.add_argument("--sizes", default="5000,25000,100000")
    parser.add_argument("--prefix", default="ab")
    parser.add_argument("--pattern", default="?ar?")
    parser.add_argument("--repeats", type=int, default=5)
    args = parser.parse_args(argv)

    sizes = [int(s) for s in args.sizes.split(",") if s.strip()]
    print(
        f"Prefix '{args.prefix}' and wildcard '{args.pattern}', "
        f"best of {args.repeats}. Milliseconds.\n"
    )
    print(f"{'':>9}  {'PREFIX':^28}  {'WILDCARD':^28}")
    print(
        f"{'words':>9}  {'trie':>8} {'scan':>8} {'hits':>8}"
        f"  {'trie':>8} {'scan':>8} {'hits':>8}"
    )
    print("-" * 72)

    rows = []
    for size in sizes:
        row = compare(size, args.prefix, args.pattern, args.repeats)
        rows.append(row)
        print(
            f"{size:>9,}  {row['prefix_trie']:>8.3f} {row['prefix_scan']:>8.3f}"
            f" {row['prefix_matches']:>8,}"
            f"  {row['wild_trie']:>8.3f} {row['wild_scan']:>8.3f}"
            f" {row['wild_matches']:>8,}"
        )

    if len(rows) > 1:
        first, last = rows[0], rows[-1]
        growth = last["size"] / first["size"]
        print(
            f"\nOver a {growth:.0f}x larger vocabulary the scan got "
            f"{last['prefix_scan'] / first['prefix_scan']:.0f}x slower and the "
            f"trie {last['prefix_trie'] / first['prefix_trie']:.0f}x."
        )
        print(
            "The scan visits every key, so it grows with the vocabulary. The\n"
            "trie walks to the prefix and then only over the answers."
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
