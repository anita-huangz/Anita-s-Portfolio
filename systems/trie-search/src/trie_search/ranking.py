"""Relevance ranking.

The index previously mapped each word to the *set* of pages containing it, and
search returned that set in alphabetical order. That is retrieval without
ranking: a page mentioning "park" once and a park directory mentioning it forty
times were indistinguishable, and a two-word query had no way to prefer pages
matching both.

BM25 fixes both. It is the standard lexical scoring function and needs three
things the set could not provide: how often a term appears on a page, how long
the page is, and how many pages contain the term at all.
"""

from __future__ import annotations

import math
from collections import Counter
from dataclasses import dataclass, field

#: Term-frequency saturation. Raising it makes repeated mentions count for
#: longer before diminishing; 1.2-2.0 is the usual range.
K1 = 1.5
#: Length normalisation, 0 (off) to 1 (full). At 0.75 a long page is penalised
#: for its length but not erased by it.
B = 0.75


@dataclass
class Posting:
    """Where a term occurs, and how often."""

    #: URL -> occurrences on that page.
    counts: dict[str, int] = field(default_factory=dict)

    @property
    def document_frequency(self) -> int:
        return len(self.counts)

    def urls(self) -> set[str]:
        """Set view, for callers that only want membership."""
        return set(self.counts)


@dataclass
class Corpus:
    """Page statistics BM25 needs, kept alongside the trie.

    The trie answers "which words look like this". The corpus answers "how
    important is this word on this page". Neither substitutes for the other.
    """

    #: URL -> total words on that page.
    lengths: dict[str, int] = field(default_factory=dict)

    @property
    def size(self) -> int:
        return len(self.lengths)

    @property
    def average_length(self) -> float:
        if not self.lengths:
            return 0.0
        return sum(self.lengths.values()) / len(self.lengths)

    def add(self, url: str, word_count: int) -> None:
        self.lengths[url] = word_count


def inverse_document_frequency(corpus_size: int, document_frequency: int) -> float:
    """How much a term's presence should count.

    A word on every page carries no signal. The 0.5 offsets are the standard
    BM25 smoothing, and the `max(..., 0)` floor matters: a term appearing on
    more than half the pages otherwise scores *negative*, and a page could
    improve its rank by not matching the query.
    """
    if corpus_size == 0 or document_frequency == 0:
        return 0.0
    raw = math.log(
        1.0 + (corpus_size - document_frequency + 0.5) / (document_frequency + 0.5)
    )
    return max(raw, 0.0)


def bm25_score(
    term_frequency: int,
    document_length: int,
    average_length: float,
    idf: float,
) -> float:
    """BM25 contribution of one term to one document."""
    if term_frequency <= 0 or idf <= 0:
        return 0.0
    if average_length <= 0:
        return idf
    normalised = K1 * (1 - B + B * (document_length / average_length))
    return idf * (term_frequency * (K1 + 1)) / (term_frequency + normalised)


@dataclass
class Hit:
    url: str
    score: float
    #: Matched term -> occurrences, so a result can explain itself.
    matched: dict[str, int] = field(default_factory=dict)

    @property
    def total_occurrences(self) -> int:
        return sum(self.matched.values())


def rank(
    postings: dict[str, Posting],
    corpus: Corpus,
    require_all: bool = False,
) -> list[Hit]:
    """Score every page that matches at least one term.

    `require_all` turns the query from OR into AND, which is what a user
    typing two words usually means.
    """
    if not postings or corpus.size == 0:
        return []

    average = corpus.average_length
    idfs = {
        term: inverse_document_frequency(corpus.size, posting.document_frequency)
        for term, posting in postings.items()
    }

    scores: dict[str, float] = {}
    matched: dict[str, dict[str, int]] = {}
    for term, posting in postings.items():
        for url, count in posting.counts.items():
            length = corpus.lengths.get(url, 0)
            scores[url] = scores.get(url, 0.0) + bm25_score(
                count, length, average, idfs[term]
            )
            matched.setdefault(url, {})[term] = count

    if require_all:
        needed = len(postings)
        scores = {u: s for u, s in scores.items() if len(matched[u]) == needed}

    hits = [
        Hit(url=url, score=round(score, 6), matched=matched[url])
        for url, score in scores.items()
    ]
    # Score descending, then URL, so equal scores order deterministically.
    hits.sort(key=lambda h: (-h.score, h.url))
    return hits


def count_words(words: list[str]) -> Counter[str]:
    return Counter(words)
