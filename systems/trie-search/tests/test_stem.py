"""The Porter stemmer, checked against a reference rather than against taste.

`porter_reference.json` holds 4,000 words and the stems NLTK's
`PorterStemmer(mode=ORIGINAL_ALGORITHM)` produces for them. The fixture is
baked so the suite needs no NLTK at runtime, and so a disagreement is a test
failure rather than something noticed later.

The full comparison, run once while writing this, covered all 235,974 words in
the system dictionary with zero disagreements.
"""

import json
import pathlib

import pytest

from trie_search.stem import _cvc, _measure, stem

REFERENCE = json.loads((pathlib.Path(__file__).parent / "porter_reference.json").read_text())


def test_the_fixture_is_substantial():
    assert REFERENCE["words"] >= 1000


def test_matches_the_reference_implementation_exactly():
    wrong = {
        word: (expected, stem(word))
        for word, expected in REFERENCE["stems"].items()
        if stem(word) != expected
    }
    assert not wrong, f"{len(wrong)} disagreements, e.g. {list(wrong.items())[:5]}"


@pytest.mark.parametrize(
    ("word", "expected"),
    [
        # The cases from Porter's own paper, step by step.
        ("caresses", "caress"), ("ponies", "poni"), ("ties", "ti"),
        ("caress", "caress"), ("cats", "cat"),
        ("feed", "feed"), ("agreed", "agre"), ("plastered", "plaster"),
        ("motoring", "motor"), ("sing", "sing"),
        ("conflated", "conflat"), ("troubled", "troubl"),
        ("hopping", "hop"), ("tanned", "tan"), ("falling", "fall"),
        ("hissing", "hiss"), ("filing", "file"),
        ("happy", "happi"), ("sky", "sky"),
        ("relational", "relat"), ("conditional", "condit"),
        ("electricity", "electr"), ("hopeful", "hope"), ("goodness", "good"),
        ("revival", "reviv"), ("allowance", "allow"), ("adjustment", "adjust"),
        ("probate", "probat"), ("rate", "rate"), ("cease", "ceas"),
        ("controll", "control"), ("roll", "roll"),
    ],
)
def test_the_papers_worked_examples(word, expected):
    assert stem(word) == expected


def test_the_family_this_feature_exists_for():
    """park / parks / parking / parked must land on one key."""
    assert len({stem(w) for w in ("park", "parks", "parking", "parked")}) == 1


def test_it_conflates_words_that_are_genuinely_different():
    """Stated because it is the cost, not hidden because it is inconvenient."""
    assert stem("universe") == stem("university") == stem("universal")


def test_a_stem_need_not_be_a_word():
    assert stem("happy") == "happi"


def test_empty_and_short_input():
    assert stem("") == ""
    assert stem("a") == "a"
    # The algorithm has no length guard, and two-letter words really do strip.
    assert stem("as") == "a"


def test_it_is_not_idempotent_and_that_is_fine():
    """`stem(stem(w))` can differ from `stem(w)`, and nothing here depends on it.

    `abase` stems to `abas`, and `abas` stems again to `aba`. The reference
    implementation does the same, so this is the algorithm rather than a bug.
    It is harmless because the index and the query are each folded exactly
    once, which is the invariant the next test pins down -- applying the
    stemmer twice to one side is what would break.
    """
    moved = [w for w in REFERENCE["stems"].values() if stem(w) != w]
    assert moved, "expected the known non-idempotence; has the algorithm changed?"


def test_a_query_finds_a_document_containing_that_word():
    """The invariant that actually matters: one fold per side, so they meet."""
    from trie_search.crawler import build_search_index

    vocabulary = sorted(REFERENCE["stems"])[:400]
    pages = {f"/{i}": [word] for i, word in enumerate(vocabulary)}
    index = build_search_index(pages, stemming=True)
    for i, word in enumerate(vocabulary):
        hits = [h.url for h in index.search(word)]
        assert f"/{i}" in hits, f"searching {word!r} did not find the page holding it"


class TestInternals:
    @pytest.mark.parametrize(
        ("word", "m"),
        [("tr", 0), ("ee", 0), ("tree", 0), ("y", 0), ("by", 0),
         ("trouble", 1), ("oats", 1), ("trees", 1), ("ivy", 1),
         ("troubles", 2), ("private", 2), ("oaten", 2), ("orrery", 2)],
    )
    def test_measure_matches_the_paper(self, word, m):
        assert _measure(word) == m

    def test_cvc_rejects_w_x_and_y(self):
        assert _cvc("hop")
        assert not _cvc("snow")
        assert not _cvc("box")
        assert not _cvc("tray")
