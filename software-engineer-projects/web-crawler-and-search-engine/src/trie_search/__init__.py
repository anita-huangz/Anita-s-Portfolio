"""A trie-backed search index built by crawling a website."""

from .crawler import CrawlResult, build_index, crawl_site, index_pages
from .fetch import Fetcher, FetchError, get_links, get_text, tokenize
from .trie import Trie, TrieNode, character_to_key

__all__ = [
    "CrawlResult",
    "FetchError",
    "Fetcher",
    "Trie",
    "TrieNode",
    "build_index",
    "character_to_key",
    "crawl_site",
    "get_links",
    "get_text",
    "index_pages",
    "tokenize",
]

__version__ = "0.2.0"
