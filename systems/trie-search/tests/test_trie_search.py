"""Tests for the trie, HTML extraction, and the crawl."""

from __future__ import annotations

import httpx
import pytest

from trie_search import (
    Corpus,
    Fetcher,
    FetchError,
    Trie,
    bm25_score,
    build_search_index,
    character_to_key,
    crawl_site,
    get_links,
    get_text,
    index_pages,
    rank,
    tokenize,
)
from trie_search.cli import search
from trie_search.ranking import inverse_document_frequency

# --------------------------------------------------------------------------- #
# character_to_key
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("char,expected", [("a", 0), ("A", 0), ("z", 25), ("Z", 25)])
def test_letters_map_to_their_alphabet_position(char, expected):
    assert character_to_key(char) == expected


@pytest.mark.parametrize("char", ["1", " ", "-", "'", "é"])
def test_non_letters_share_the_other_bucket(char):
    assert character_to_key(char) == 26


def test_multi_character_input_is_rejected():
    with pytest.raises(ValueError, match="single character"):
        character_to_key("ab")


# --------------------------------------------------------------------------- #
# Trie as a mapping
# --------------------------------------------------------------------------- #


def test_set_and_get():
    trie = Trie()
    trie["cat"] = 1
    assert trie["cat"] == 1


def test_missing_key_raises_keyerror():
    with pytest.raises(KeyError):
        Trie()["nope"]


def test_prefix_of_a_key_is_not_itself_a_key():
    """'ca' walks real nodes but was never inserted."""
    trie = Trie({"cat": 1})
    with pytest.raises(KeyError):
        trie["ca"]


def test_overwrite_does_not_change_length():
    trie = Trie({"cat": 1})
    trie["cat"] = 2
    assert trie["cat"] == 2
    assert len(trie) == 1


def test_delete():
    trie = Trie({"cat": 1, "car": 2})
    del trie["cat"]
    assert len(trie) == 1
    assert "cat" not in trie
    assert trie["car"] == 2


def test_deleting_a_missing_key_raises():
    with pytest.raises(KeyError):
        del Trie()["nope"]


def test_non_string_key_is_a_typeerror():
    with pytest.raises(TypeError, match="must be strings"):
        Trie()[42] = 1


def test_contains():
    trie = Trie({"cat": 1})
    assert "cat" in trie
    assert "dog" not in trie


def test_iteration_yields_keys_not_pairs():
    """The old __iter__ yielded tuples, which broke every Mapping mixin."""
    trie = Trie({"cat": 1, "car": 2})
    assert sorted(trie) == ["car", "cat"]
    assert all(isinstance(k, str) for k in trie)


def test_items_values_and_dict_conversion_work():
    """These are built on __iter__, so a tuple-yielding __iter__ broke them all."""
    trie = Trie({"cat": 1, "car": 2})
    assert dict(trie) == {"cat": 1, "car": 2}
    assert sorted(trie.items()) == [("car", 2), ("cat", 1)]
    assert sorted(trie.values()) == [1, 2]
    assert sorted(trie.keys()) == ["car", "cat"]


def test_keys_come_back_in_alphabetical_order():
    trie = Trie({"pear": 1, "apple": 2, "fig": 3})
    assert list(trie) == ["apple", "fig", "pear"]


def test_get_and_setdefault_from_the_mixin():
    trie = Trie({"cat": 1})
    assert trie.get("cat") == 1
    assert trie.get("dog", "fallback") == "fallback"
    assert trie.setdefault("dog", 9) == 9
    assert trie["dog"] == 9


def test_empty_string_is_a_valid_key():
    trie = Trie()
    trie[""] = "root"
    assert trie[""] == "root"
    assert len(trie) == 1


# --------------------------------------------------------------------------- #
# Lossy alphabet folding -- documented behaviour
# --------------------------------------------------------------------------- #


def test_keys_are_case_insensitive():
    trie = Trie()
    trie["Cat"] = 1
    assert trie["cat"] == 1
    assert trie["CAT"] == 1
    assert len(trie) == 1


def test_non_letters_collapse_into_one_bucket():
    """"don't" and "don_t" fold to the same path -- lossy, and intentional."""
    trie = Trie()
    trie["don't"] = 1
    assert trie["don_t"] == 1


def test_original_keys_recovers_the_inserted_text():
    trie = Trie()
    trie["Don't"] = 1
    assert list(trie.original_keys()) == ["Don't"]
    assert list(trie) == ["don_t"]   # folded form


# --------------------------------------------------------------------------- #
# Prefix and wildcard search
# --------------------------------------------------------------------------- #


def test_prefix_search():
    trie = Trie({"cat": 1, "car": 2, "cart": 3, "dog": 4})
    assert sorted(trie.keys_with_prefix("ca")) == ["car", "cart", "cat"]


def test_prefix_search_with_no_matches_is_empty():
    assert list(Trie({"cat": 1}).keys_with_prefix("zz")) == []


def test_empty_prefix_returns_everything():
    trie = Trie({"cat": 1, "dog": 2})
    assert sorted(trie.keys_with_prefix("")) == ["cat", "dog"]


def test_wildcard_uses_question_mark_as_documented():
    """The implementation matched '*' while the docs promised '?'."""
    trie = Trie({"cat": 1, "cot": 2, "cut": 3, "cart": 4})
    assert sorted(trie.wildcard_search("c?t")) == [("cat", 1), ("cot", 2), ("cut", 3)]


def test_wildcard_matches_exactly_one_character():
    trie = Trie({"cat": 1, "cart": 2})
    assert [k for k, _ in trie.wildcard_search("c?t")] == ["cat"]


def test_multiple_wildcards():
    trie = Trie({"ab": 1, "cd": 2, "abc": 3})
    assert sorted(k for k, _ in trie.wildcard_search("??")) == ["ab", "cd"]


def test_wildcard_with_no_wildcard_is_an_exact_lookup():
    trie = Trie({"cat": 1, "car": 2})
    assert list(trie.wildcard_search("cat")) == [("cat", 1)]


def test_wildcard_that_matches_nothing():
    assert list(Trie({"cat": 1}).wildcard_search("z?z")) == []


# --------------------------------------------------------------------------- #
# HTML handling
# --------------------------------------------------------------------------- #

PAGE = """
<html><head><style>body{color:red}</style><script>var x = 'javascript';</script></head>
<body><h1>Parks</h1><p>Visit the park today.</p>
<a href="/parks/1">One</a><a href="/parks/2">Two</a><a href="/parks/1#map">Again</a>
</body></html>
"""


def test_script_and_style_are_not_indexed():
    """text_content() alone indexes a page's JavaScript as searchable words."""
    text = get_text(PAGE)
    assert "Parks" in text
    assert "javascript" not in text
    assert "color" not in text


def test_links_are_made_absolute():
    links = get_links(PAGE, "https://example.com/start")
    assert "https://example.com/parks/1" in links


def test_tokenize_lowercases_and_strips_punctuation():
    assert tokenize("Visit the Park, today!") == ["visit", "the", "park", "today"]


def test_tokenize_drops_punctuation_only_tokens():
    assert tokenize("hello -- world") == ["hello", "world"]


def test_tokenize_keeps_internal_punctuation():
    assert tokenize("well-known state-of-the-art") == ["well-known", "state-of-the-art"]


def test_adjacent_elements_are_not_glued_together():
    """text_content() would give 'Calpha' and lose both words."""
    assert tokenize(get_text("<a>C</a><p>alpha page</p>")) == ["c", "alpha", "page"]


# --------------------------------------------------------------------------- #
# Fetcher
# --------------------------------------------------------------------------- #


def fetcher_for(handler, prefixes=("https://example.com",)) -> Fetcher:
    transport = httpx.MockTransport(handler)
    return Fetcher(
        allowed_prefixes=prefixes, client=httpx.Client(transport=transport)
    )


def test_http_urls_are_refused():
    with pytest.raises(FetchError, match="https"):
        Fetcher().fetch("http://example.com")


def test_urls_outside_the_allowlist_are_refused():
    with pytest.raises(FetchError, match="allowed prefixes"):
        Fetcher().fetch("https://evil.test/page")


def test_a_server_error_becomes_a_fetch_error():
    f = fetcher_for(lambda r: httpx.Response(500))
    with pytest.raises(FetchError, match="failed"):
        f.fetch("https://example.com/x")


# --------------------------------------------------------------------------- #
# Crawling
# --------------------------------------------------------------------------- #

SITE = {
    "https://example.com/": '<a href="/a">A</a><a href="/b">B</a><p>root page</p>',
    "https://example.com/a": '<a href="/c">C</a><p>alpha page</p>',
    "https://example.com/b": "<p>beta page</p>",
    "https://example.com/c": "<p>gamma page</p>",
}


def site_handler(request: httpx.Request) -> httpx.Response:
    body = SITE.get(str(request.url))
    return httpx.Response(200, text=body) if body else httpx.Response(404)


def test_depth_zero_fetches_only_the_start_page():
    result = crawl_site("https://example.com/", 0, fetcher_for(site_handler))
    assert set(result.pages) == {"https://example.com/"}


def test_depth_one_follows_direct_links():
    result = crawl_site("https://example.com/", 1, fetcher_for(site_handler))
    assert set(result.pages) == {
        "https://example.com/", "https://example.com/a", "https://example.com/b"
    }


def test_depth_two_goes_one_hop_further():
    result = crawl_site("https://example.com/", 2, fetcher_for(site_handler))
    assert "https://example.com/c" in result.pages


def test_a_page_is_fetched_only_once():
    seen: list[str] = []

    def counting(request):
        seen.append(str(request.url))
        return site_handler(request)

    crawl_site("https://example.com/", 2, fetcher_for(counting))
    assert len(seen) == len(set(seen))


def test_fragments_do_not_cause_a_refetch():
    """/page and /page#section are the same document."""
    page = '<a href="/a">A</a><a href="/a#section">Same</a>'
    fetched: list[str] = []

    def handler(request):
        fetched.append(str(request.url))
        return httpx.Response(200, text=page)

    result = crawl_site("https://example.com/", 1, fetcher_for(handler))
    assert "https://example.com/a#section" not in result.pages
    assert fetched.count("https://example.com/a") == 1


def test_two_crawls_in_one_process_are_independent():
    """A module-level visited set made the second crawl return nothing."""
    first = crawl_site("https://example.com/", 1, fetcher_for(site_handler))
    second = crawl_site("https://example.com/", 1, fetcher_for(site_handler))
    assert set(first.pages) == set(second.pages)
    assert len(second.pages) > 0


def test_unfetchable_pages_are_reported_not_swallowed():
    def flaky(request):
        if str(request.url).endswith("/b"):
            return httpx.Response(500)
        return site_handler(request)

    result = crawl_site("https://example.com/", 1, fetcher_for(flaky))
    assert "https://example.com/b" in result.failures
    assert "https://example.com/a" in result.pages


def test_offsite_links_are_not_followed():
    page = '<a href="https://evil.test/x">Away</a><p>root</p>'
    result = crawl_site(
        "https://example.com/", 1, fetcher_for(lambda r: httpx.Response(200, text=page))
    )
    assert set(result.pages) == {"https://example.com/"}


def test_negative_depth_is_rejected():
    with pytest.raises(ValueError, match="non-negative"):
        crawl_site("https://example.com/", -1)


def test_max_pages_caps_the_crawl():
    result = crawl_site("https://example.com/", 5, fetcher_for(site_handler), max_pages=2)
    assert len(result.pages) == 2


# --------------------------------------------------------------------------- #
# Index
# --------------------------------------------------------------------------- #


def test_index_maps_words_to_every_page_they_appear_on():
    index = index_pages({"u1": ["park", "tree"], "u2": ["park", "lake"]})
    assert index["park"] == {"u1", "u2"}
    assert index["tree"] == {"u1"}


def test_index_search_by_prefix():
    index = index_pages({"u1": ["park", "parking", "lake"]})
    assert [w for w, _ in search(index, "park")] == ["park", "parking"]


def test_index_search_by_wildcard():
    index = index_pages({"u1": ["cat", "cot", "dog"]})
    assert [w for w, _ in search(index, "c?t")] == ["cat", "cot"]


def test_empty_query_returns_nothing():
    assert search(index_pages({"u1": ["cat"]}), "  ") == []


def test_end_to_end_crawl_then_search():
    index = index_pages(crawl_site("https://example.com/", 2, fetcher_for(site_handler)).pages)
    assert index["page"] == {
        "https://example.com/", "https://example.com/a",
        "https://example.com/b", "https://example.com/c",
    }
    assert [w for w, _ in search(index, "al?ha")] == ["alpha"]


# --------------------------------------------------------------------------- #
# BM25 ranking
# --------------------------------------------------------------------------- #

RANK_PAGES = {
    # A dedicated page: "park" many times, short document.
    "https://example.com/parks": ["park"] * 12 + ["visit", "today"],
    # A passing mention inside a long page.
    "https://example.com/about": ["about", "us"] * 60 + ["park"],
    # Two terms, both present.
    "https://example.com/dogpark": ["dog", "park", "dog", "park", "rules"],
    # Only the other term.
    "https://example.com/dogs": ["dog"] * 8 + ["breeds"],
}


def test_more_mentions_on_a_shorter_page_ranks_higher():
    """The gap a set-valued index could not express."""
    index = build_search_index(RANK_PAGES)
    hits = index.search("park")
    assert hits[0].url == "https://example.com/parks"
    # The passing mention on a long page must not tie with the dedicated one.
    scores = {h.url: h.score for h in hits}
    assert scores["https://example.com/parks"] > scores["https://example.com/about"]


def test_ranking_is_not_alphabetical():
    index = build_search_index(RANK_PAGES)
    urls = [h.url for h in index.search("park")]
    assert urls != sorted(urls)


def test_two_word_query_requires_both_by_default():
    index = build_search_index(RANK_PAGES)
    urls = {h.url for h in index.search("dog park")}
    assert urls == {"https://example.com/dogpark"}


def test_two_word_query_can_be_widened_to_or():
    index = build_search_index(RANK_PAGES)
    urls = {h.url for h in index.search("dog park", require_all=False)}
    assert "https://example.com/dogs" in urls
    assert "https://example.com/parks" in urls


def test_a_query_term_absent_everywhere_yields_nothing():
    index = build_search_index(RANK_PAGES)
    assert index.search("park unicorn") == []


def test_hits_explain_themselves():
    index = build_search_index(RANK_PAGES)
    top = index.search("park")[0]
    assert top.matched == {"park": 12}
    assert top.total_occurrences == 12


def test_prefix_query_expands():
    index = build_search_index({"u": ["park", "parking", "parkway", "dog"]})
    urls = [h.url for h in index.search("park*")]
    assert urls == ["u"]
    assert set(index.search("park*")[0].matched) == {"park", "parking", "parkway"}


def test_wildcard_query_expands():
    index = build_search_index({"u": ["cat", "cot", "cut", "dog"]})
    matched = index.search("c?t")[0].matched
    assert set(matched) == {"cat", "cot", "cut"}


def test_ranked_empty_query_returns_nothing():
    index = build_search_index(RANK_PAGES)
    assert index.search("   ") == []


def test_limit_caps_the_result_count():
    pages = {f"u{i}": ["park"] * (i + 1) for i in range(30)}
    assert len(build_search_index(pages).search("park", limit=5)) == 5


def test_a_term_on_every_page_cannot_score_negatively():
    """Without the IDF floor, a common term makes matching pages rank below
    non-matching ones, which is nonsense."""
    pages = {f"u{i}": ["the", "quick", f"w{i}"] for i in range(10)}
    index = build_search_index(pages)
    for hit in index.search("the"):
        assert hit.score >= 0


def test_idf_falls_as_a_term_becomes_common():
    rare = inverse_document_frequency(1000, 1)
    common = inverse_document_frequency(1000, 900)
    assert rare > common >= 0


def test_bm25_saturates_with_repetition():
    """The tenth mention should add less than the second."""
    idf = inverse_document_frequency(100, 10)
    first = bm25_score(1, 100, 100, idf)
    second = bm25_score(2, 100, 100, idf)
    tenth = bm25_score(10, 100, 100, idf)
    eleventh = bm25_score(11, 100, 100, idf)
    assert (second - first) > (eleventh - tenth) > 0


def test_bm25_penalises_length():
    idf = inverse_document_frequency(100, 10)
    short = bm25_score(3, 50, 100, idf)
    long = bm25_score(3, 400, 100, idf)
    assert short > long


def test_bm25_of_an_absent_term_is_zero():
    assert bm25_score(0, 100, 100, 1.0) == 0.0


def test_ranking_an_empty_corpus_is_empty():
    assert rank({}, Corpus()) == []


def test_search_index_reports_its_size():
    index = build_search_index(RANK_PAGES)
    assert index.pages == len(RANK_PAGES)
    assert len(index) > 0


def test_equal_scores_break_ties_deterministically():
    pages = {"https://b.test": ["park"], "https://a.test": ["park"]}
    index = build_search_index(pages)
    first = [h.url for h in index.search("park")]
    second = [h.url for h in build_search_index(pages).search("park")]
    assert first == second


def test_end_to_end_crawl_then_ranked_search():
    result = crawl_site("https://example.com/", 2, fetcher_for(site_handler))
    index = build_search_index(result.pages)
    hits = index.search("page")
    assert len(hits) == 4
    assert all(h.score > 0 for h in hits)

    # Every page mentions "page" exactly once, so the only thing separating
    # them is length — and the shortest page wins. Set-valued indexing could
    # not express that distinction at all.
    assert all(h.matched == {"page": 1} for h in hits)
    lengths = [index.corpus.lengths[h.url] for h in hits]
    assert lengths == sorted(lengths)
