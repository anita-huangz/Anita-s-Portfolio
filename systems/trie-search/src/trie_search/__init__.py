"""A trie-backed search index built by crawling a website."""

from .crawler import (
    CrawlResult,
    SearchIndex,
    build_index,
    build_search_index,
    crawl_site,
    index_pages,
)
from .fetch import Fetcher, FetchError, get_links, get_text, tokenize
from .ranking import Corpus, Hit, Posting, bm25_score, rank
from .trie import Trie, TrieNode, character_to_key

__all__ = [
    "Corpus",
    "CrawlResult",
    "FetchError",
    "Fetcher",
    "Hit",
    "Posting",
    "SearchIndex",
    "Trie",
    "TrieNode",
    "bm25_score",
    "build_index",
    "build_search_index",
    "character_to_key",
    "crawl_site",
    "get_links",
    "get_text",
    "index_pages",
    "rank",
    "tokenize",
]

__version__ = "0.2.0"
