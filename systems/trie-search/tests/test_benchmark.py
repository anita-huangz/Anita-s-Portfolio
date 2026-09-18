"""The benchmark is quoted in the README, so it has to keep working.

These do not assert timings -- a test that fails when the machine is busy is
worse than no test. They assert the things the README's argument rests on: that
both approaches find the same words, and that the harness reports honestly.
"""

import pytest

from trie_search.benchmark import compare, main, vocabulary
from trie_search.trie import Trie


def test_vocabulary_is_distinct_and_reproducible():
    first = vocabulary(500)
    assert len(first) == 500
    assert len(set(first)) == 500
    assert first == vocabulary(500), "the table must be reproducible between runs"


def test_vocabulary_words_are_within_the_stated_shape():
    assert all(3 <= len(w) <= 10 and w.isalpha() and w.islower()
               for w in vocabulary(300))


def test_the_trie_and_the_scan_agree_on_prefixes():
    """The comparison is only meaningful if both find the same answers."""
    keys = vocabulary(3000)
    trie = Trie({k: i for i, k in enumerate(keys)})
    for prefix in ("a", "ab", "zz", "qqq"):
        assert sorted(trie.keys_with_prefix(prefix)) == sorted(
            k for k in keys if k.startswith(prefix)
        ), prefix


def test_the_trie_and_the_scan_agree_on_wildcards():
    import re

    keys = vocabulary(3000)
    trie = Trie({k: i for i, k in enumerate(keys)})
    for pattern in ("?ar?", "a?c", "??"):
        expected = [k for k in keys if re.fullmatch(pattern.replace("?", "."), k)]
        assert sorted(w for w, _ in trie.wildcard_search(pattern)) == sorted(expected), (
            pattern
        )


def test_compare_reports_the_same_hit_count_for_both_methods():
    row = compare(2000, "ab", "?ar?", repeats=1)
    keys = vocabulary(2000)
    assert row["prefix_matches"] == sum(1 for k in keys if k.startswith("ab"))
    assert row["size"] == 2000
    assert row["prefix_trie"] >= 0 and row["prefix_scan"] >= 0


@pytest.mark.parametrize("argv", [
    ["--sizes", "500"],
    ["--sizes", "500,1000", "--prefix", "a", "--pattern", "??", "--repeats", "1"],
])
def test_the_command_line_runs(argv, capsys):
    assert main(argv) == 0
    out = capsys.readouterr().out
    assert "trie" in out and "scan" in out
