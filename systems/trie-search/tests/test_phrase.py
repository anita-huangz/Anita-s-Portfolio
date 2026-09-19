"""Phrase search: adjacency, and the cases where it must say no.

The interesting tests are the negatives. A phrase search that returns pages
containing both words is not a phrase search, it is the bag-of-words query with
extra syntax, and it would look like it worked.
"""

import pytest

from trie_search.crawler import build_search_index
from trie_search.ranking import MissingPositions, Posting, phrase_matches

PAGES = {
    "/adjacent": ["the", "park", "hours", "are", "posted", "at", "the", "gate"],
    "/apart": ["opening", "hours", "are", "listed", "for", "every", "park"],
    "/repeated": ["park", "hours", "park", "hours", "park", "hours"],
    "/reversed": ["hours", "park"],
    "/single": ["park"],
}


@pytest.fixture
def index():
    return build_search_index(PAGES)


def urls(hits):
    return {h.url for h in hits}


class TestAdjacency:
    def test_finds_only_pages_with_the_words_adjacent(self, index):
        assert urls(index.search('"park hours"')) == {"/adjacent", "/repeated"}

    def test_the_unquoted_query_finds_more(self, index):
        """The contrast is the point: /apart has both words, not the phrase."""
        assert "/apart" in urls(index.search("park hours"))
        assert "/apart" not in urls(index.search('"park hours"'))

    def test_order_matters(self, index):
        assert urls(index.search('"hours park"')) == {"/reversed", "/repeated"}

    def test_counts_every_occurrence(self, index):
        hit = next(h for h in index.search('"park hours"') if h.url == "/repeated")
        assert hit.matched == {"park hours": 3}

    def test_more_occurrences_rank_higher(self, index):
        ranked = [h.url for h in index.search('"park hours"')]
        assert ranked[0] == "/repeated"

    def test_a_missing_word_means_no_phrase(self, index):
        assert index.search('"park zebra"') == []

    def test_a_phrase_longer_than_the_page(self, index):
        assert index.search('"park hours are posted at the gate tomorrow"') == []

    def test_a_single_quoted_word_is_an_ordinary_search(self, index):
        assert urls(index.search('"park"')) == urls(index.search("park"))

    def test_an_empty_phrase_returns_nothing(self, index):
        assert index.search('""') == []


class TestPhraseMatches:
    def test_counts_runs_directly(self):
        a, b = Posting(), Posting()
        a.record("/x", [0, 5, 9])
        b.record("/x", [1, 6, 20])
        assert phrase_matches([a, b], "/x") == 2

    def test_overlapping_runs_of_a_repeated_word(self):
        # "ha ha ha": the phrase "ha ha" occurs twice, not three times.
        a = Posting()
        a.record("/x", [0, 1, 2])
        assert phrase_matches([a, a], "/x") == 2

    def test_a_page_without_the_term(self):
        a, b = Posting(), Posting()
        a.record("/x", [0])
        b.record("/y", [1])
        assert phrase_matches([a, b], "/x") == 0

    def test_no_postings(self):
        assert phrase_matches([], "/x") == 0


class TestWithoutPositions:
    def test_an_index_built_without_positions_says_so(self):
        index = build_search_index(PAGES, positions=False)
        assert not index.has_positions
        with pytest.raises(MissingPositions, match="without positions"):
            index.search('"park hours"')

    def test_ordinary_search_still_works_without_positions(self):
        index = build_search_index(PAGES, positions=False)
        assert urls(index.search("park hours"))

    def test_counts_agree_whether_or_not_positions_were_recorded(self):
        """The two build paths must not disagree about term frequency."""
        with_pos = build_search_index(PAGES, positions=True)
        without = build_search_index(PAGES, positions=False)
        for term in ("park", "hours", "the"):
            a, b = with_pos.posting(term), without.posting(term)
            assert a.counts == b.counts, term

    def test_positions_and_counts_stay_in_step(self):
        index = build_search_index(PAGES)
        for term in ("park", "hours", "the"):
            posting = index.posting(term)
            for url, count in posting.counts.items():
                assert len(posting.positions[url]) == count


class TestWithStemming:
    def test_a_phrase_works_on_stems(self):
        pages = {"/a": ["the", "parking", "hours", "are", "posted"]}
        index = build_search_index(pages, stemming=True)
        assert urls(index.search('"park hour"')) == {"/a"}

    def test_positions_survive_stemming(self):
        pages = {"/a": ["parks", "parking", "parked"]}
        index = build_search_index(pages, stemming=True)
        posting = index.posting("park")
        assert posting.positions["/a"] == [0, 1, 2]
