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

from .crawler import build_search_index
from .trie import Trie

#: Fixed so the table is reproducible between runs and machines.
SEED = 0


def vocabulary_words(count: int, seed: int = SEED) -> list[str]:
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
    keys = vocabulary_words(size)
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


#: Roots that actually inflect, so the corpus has surface forms for stemming to
#: collapse. Random letter strings have no morphology, and measuring a stemmer
#: on them would report that it does nothing -- which says more about the
#: generator than about the stemmer.
_ROOTS = [
    "park", "walk", "open", "close", "list", "report", "plan", "visit",
    "manage", "connect", "operate", "inform", "develop", "improve", "record",
    "govern", "provide", "require", "publish", "announce",
]
_ENDINGS = ["", "s", "ed", "ing", "er", "ers", "ment", "ments"]


def _inflected(count: int, seed: int = SEED) -> list[str]:
    """A vocabulary with real morphology, padded with filler to `count`."""
    words = [root + ending for root in _ROOTS for ending in _ENDINGS]
    if count > len(words):
        words += vocabulary_words(count - len(words), seed)
    return words[:count]


def _corpus(pages: int, words_per_page: int, seed: int = SEED) -> dict[str, list[str]]:
    """Pages of Zipf-ish text: a few words everywhere, a long tail once each."""
    rng = random.Random(seed)
    vocabulary = _inflected(max(words_per_page, 2000), seed)
    out = {}
    for page in range(pages):
        words = []
        for _ in range(words_per_page):
            # Rank-biased pick: index 0 is far likelier than index 1000.
            rank = min(int(rng.paretovariate(1.2)) - 1, len(vocabulary) - 1)
            words.append(vocabulary[rank])
        out[f"/page-{page}"] = words
    return out


def measure_index(pages: int, words_per_page: int) -> list[dict[str, object]]:
    """What positions and stemming cost to build and to hold."""
    corpus = _corpus(pages, words_per_page)
    total_words = sum(len(w) for w in corpus.values())
    rows = []
    for label, kwargs in (
        ("counts only", {"positions": False}),
        ("with positions", {"positions": True}),
        ("positions + stemming", {"positions": True, "stemming": True}),
    ):
        started = time.perf_counter()
        index = build_search_index(corpus, **kwargs)
        build_ms = (time.perf_counter() - started) * 1000
        rows.append({
            "label": label,
            "terms": len(index.trie),
            "bytes": _index_bytes(index),
            "build_ms": build_ms,
            "total_words": total_words,
        })
    return rows


def _index_bytes(index) -> int:
    """Roughly what the postings occupy: counts, plus offsets when recorded.

    Deliberately measures the payload rather than calling `sys.getsizeof` on a
    nested structure, which reports the container and not what it holds.
    """
    total = 0
    for term in index.trie:
        posting = index.posting(term)
        if posting is None:
            continue
        total += len(term) + 8 * len(posting.counts)
        total += 8 * sum(len(v) for v in posting.positions.values())
    return total


def print_index_cost(pages: int, words_per_page: int) -> None:
    rows = measure_index(pages, words_per_page)
    baseline = rows[0]
    print(
        f"\n{pages:,} pages x {words_per_page:,} words "
        f"= {rows[0]['total_words']:,} tokens.\n"
    )
    print(f"{'index':<22} {'terms':>8} {'payload':>12} {'vs counts':>10} {'build':>9}")
    print("-" * 66)
    for row in rows:
        ratio = row["bytes"] / baseline["bytes"]
        print(
            f"{row['label']:<22} {row['terms']:>8,} {row['bytes'] / 1024:>10,.0f} KB "
            f"{ratio:>9.1f}x {row['build_ms']:>7.0f} ms"
        )
    stemmed = rows[-1]["terms"]
    plain = rows[0]["terms"]
    print(
        "\nPositions cost roughly one entry per *token*, where counts cost one"
        "\nper distinct term per page -- so the gap widens with page length, not"
        "\nwith vocabulary."
    )
    if stemmed < plain:
        print(
            f"Stemming folds {plain:,} terms into {stemmed:,} "
            f"({1 - stemmed / plain:.0%} fewer), which is the same collapsing "
            f"that\nmakes a search for one surface form find the others."
        )
    else:
        print(
            "Stemming did not reduce the term count on this corpus, which means"
            "\nthe generated vocabulary has no inflections to collapse."
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Trie against a dictionary scan.")
    parser.add_argument("--sizes", default="5000,25000,100000")
    parser.add_argument("--prefix", default="ab")
    parser.add_argument("--pattern", default="?ar?")
    parser.add_argument("--repeats", type=int, default=5)
    parser.add_argument(
        "--index", action="store_true",
        help="Measure what positions and stemming cost to build and hold.",
    )
    parser.add_argument("--pages", type=int, default=400)
    parser.add_argument("--words-per-page", type=int, default=600)
    args = parser.parse_args(argv)

    if args.index:
        print_index_cost(args.pages, args.words_per_page)
        return 0

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
