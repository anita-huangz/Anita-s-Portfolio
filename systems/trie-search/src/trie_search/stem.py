"""The Porter stemmer, written out.

Without it the index treats `park`, `parks` and `parking` as three unrelated
keys, so a search for one misses pages that only use another. The wildcard
partly covers this -- `par*` finds all three -- but only if the searcher knows
to type it, and it over-matches badly: `par*` also returns `parliament`,
`parenthesis` and `parasite`.

Stemming folds the surface forms to a common root at index time and does the
same to the query, so `parks` and `park` land on the same posting without
`parliament` joining them.

It is a heuristic, not linguistics, and it is wrong in interesting ways. The
stem is often not a word -- `happy` becomes `happi`, `relational` becomes
`relat` -- which does not matter because it is only ever compared against
other stems, never shown. And it conflates words that are genuinely different:
`universe`, `university` and `universal` all reduce to `univers`. That is the
trade the algorithm makes on purpose, and the reason stemming is optional here
rather than always on.

Reference: M.F. Porter, *An algorithm for suffix stripping*, Program 14(3),
1980. The step numbering below is his.
"""

from __future__ import annotations

VOWELS = frozenset("aeiou")


def _is_consonant(word: str, index: int) -> bool:
    """`y` is the awkward one: a consonant unless preceded by a consonant."""
    letter = word[index]
    if letter in VOWELS:
        return False
    if letter == "y":
        return index == 0 or not _is_consonant(word, index - 1)
    return True


def _measure(stem: str) -> int:
    """Porter's *m*: how many vowel-consonant sequences the stem contains.

    This is the algorithm's notion of "long enough to strip from". `tree` has
    m=0 and keeps its suffixes; `trouble` has m=1; `troubles` stripped to
    `trouble` is still a real word, while stripping `tree` would not be.
    """
    count = 0
    seen_vowel = False
    for i in range(len(stem)):
        if _is_consonant(stem, i):
            if seen_vowel:
                count += 1
                seen_vowel = False
        else:
            seen_vowel = True
    return count


def _has_vowel(stem: str) -> bool:
    return any(not _is_consonant(stem, i) for i in range(len(stem)))


def _ends_double_consonant(stem: str) -> bool:
    return (
        len(stem) >= 2
        and stem[-1] == stem[-2]
        and _is_consonant(stem, len(stem) - 1)
    )


def _cvc(stem: str) -> bool:
    """Consonant-vowel-consonant where the last is not w, x or y.

    Porter's `*o` condition. It marks a short word whose final consonant would
    need doubling if a suffix were added -- `hop` -> `hopping` -- and so one
    that should take an `e` back when a suffix is removed.
    """
    if len(stem) < 3:
        return False
    if not (
        _is_consonant(stem, len(stem) - 3)
        and not _is_consonant(stem, len(stem) - 2)
        and _is_consonant(stem, len(stem) - 1)
    ):
        return False
    return stem[-1] not in "wxy"


def _replace(word: str, suffix: str, replacement: str, min_measure: int) -> str | None:
    """Swap `suffix` for `replacement` if the remaining stem is long enough."""
    if not word.endswith(suffix):
        return None
    stem = word[: len(word) - len(suffix)]
    if _measure(stem) > min_measure:
        return stem + replacement
    return None


_STEP2 = [
    ("ational", "ate"), ("tional", "tion"), ("enci", "ence"), ("anci", "ance"),
    ("izer", "ize"), ("abli", "able"), ("alli", "al"), ("entli", "ent"),
    ("eli", "e"), ("ousli", "ous"), ("ization", "ize"), ("ation", "ate"),
    ("ator", "ate"), ("alism", "al"), ("iveness", "ive"), ("fulness", "ful"),
    ("ousness", "ous"), ("aliti", "al"), ("iviti", "ive"), ("biliti", "ble"),
]
# Deliberately the 1980 paper and not Porter's later revisions. He went on to
# add `BLI -> BLE` (generalising `ABLI -> ABLE`) and `LOGI -> LOG`, which change
# roughly one word in 220 -- `accessibly` and everything ending `-ology`. Either
# set is defensible; implementing one and citing the other is not, and
# `test_stem.py` checks this against a reference for the version named above.

_STEP3 = [
    ("icate", "ic"), ("ative", ""), ("alize", "al"), ("iciti", "ic"),
    ("ical", "ic"), ("ful", ""), ("ness", ""),
]

_STEP4 = [
    "al", "ance", "ence", "er", "ic", "able", "ible", "ant", "ement",
    "ment", "ent", "ou", "ism", "ate", "iti", "ous", "ive", "ize",
]


def stem(word: str) -> str:
    """Reduce a word to its Porter stem. Short words are returned unchanged."""
    word = word.lower()
    if not word:
        return word

    # Step 1a -- plurals.
    if word.endswith("sses") or word.endswith("ies"):
        word = word[:-2]
    elif word.endswith("ss"):
        pass
    elif word.endswith("s"):
        word = word[:-1]

    # Step 1b -- past tense and progressive.
    second_or_third = False
    if word.endswith("eed"):
        if _measure(word[:-3]) > 0:
            word = word[:-1]
    elif word.endswith("ed") and _has_vowel(word[:-2]):
        word = word[:-2]
        second_or_third = True
    elif word.endswith("ing") and _has_vowel(word[:-3]):
        word = word[:-3]
        second_or_third = True

    if second_or_third:
        if word.endswith(("at", "bl", "iz")):
            word += "e"
        elif _ends_double_consonant(word) and word[-1] not in "lsz":
            word = word[:-1]
        elif _measure(word) == 1 and _cvc(word):
            word += "e"

    # Step 1c -- terminal y to i.
    if word.endswith("y") and _has_vowel(word[:-1]):
        word = word[:-1] + "i"

    # Steps 2 and 3 -- derivational suffixes, longest match first.
    for table in (_STEP2, _STEP3):
        for suffix, replacement in table:
            swapped = _replace(word, suffix, replacement, 0)
            if swapped is not None:
                word = swapped
                break

    # Step 4 -- strip the suffix entirely, but only from a long stem.
    for suffix in _STEP4:
        if word.endswith(suffix):
            stripped = word[: len(word) - len(suffix)]
            if suffix in ("ion",) and not stripped.endswith(("s", "t")):
                continue
            if _measure(stripped) > 1:
                word = stripped
            break
    else:
        if word.endswith("ion"):
            stripped = word[:-3]
            if _measure(stripped) > 1 and stripped.endswith(("s", "t")):
                word = stripped

    # Step 5a -- a trailing e.
    if word.endswith("e"):
        measure = _measure(word[:-1])
        if measure > 1 or (measure == 1 and not _cvc(word[:-1])):
            word = word[:-1]

    # Step 5b -- a doubled l.
    if _measure(word) > 1 and _ends_double_consonant(word) and word.endswith("l"):
        word = word[:-1]

    return word
