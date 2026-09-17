"""Breadth-first crawl and index construction."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field

from .fetch import Fetcher, FetchError, get_links, get_text, tokenize
from .trie import Trie


@dataclass
class CrawlResult:
    pages: dict[str, list[str]] = field(default_factory=dict)
    #: URLs that were reached but could not be fetched, with the reason.
    failures: dict[str, str] = field(default_factory=dict)

    @property
    def word_count(self) -> int:
        return sum(len(words) for words in self.pages.values())


def crawl_site(
    start_url: str,
    max_depth: int = 1,
    fetcher: Fetcher | None = None,
    max_pages: int = 200,
) -> CrawlResult:
    """Crawl from `start_url`, following links up to `max_depth` hops.

    Depth 0 fetches only the start page; depth 1 also fetches its links.
    A page is visited at most once per call.
    """
    if max_depth < 0:
        raise ValueError("max_depth must be non-negative")

    fetcher = fetcher or Fetcher()
    result = CrawlResult()
    # Owned by the call, not the module: two crawls in one process are
    # independent, which the previous global `_seen_already` made impossible.
    seen: set[str] = {start_url}
    queue: deque[tuple[str, int]] = deque([(start_url, 0)])

    while queue and len(result.pages) < max_pages:
        url, depth = queue.popleft()

        try:
            html = fetcher.fetch(url)
        except FetchError as exc:
            # Recorded rather than swallowed: a crawl that quietly returns
            # nothing is indistinguishable from a site with no content.
            result.failures[url] = str(exc)
            continue

        result.pages[url] = tokenize(get_text(html))

        if depth >= max_depth:
            continue

        for link in get_links(html, url):
            # Strip fragments: /page and /page#section are the same document.
            link = link.split("#", 1)[0]
            if link and link not in seen and fetcher.is_allowed(link):
                seen.add(link)
                queue.append((link, depth + 1))

    return result


def build_index(
    start_url: str,
    max_depth: int = 1,
    fetcher: Fetcher | None = None,
) -> Trie:
    """Crawl a site and return a trie mapping each word to the URLs it appears on."""
    result = crawl_site(start_url, max_depth, fetcher)
    return index_pages(result.pages)


def index_pages(pages: dict[str, list[str]]) -> Trie:
    """Build the word -> {urls} index from already-crawled pages."""
    index: Trie = Trie()
    for url, words in pages.items():
        for word in words:
            urls = index.get(word)
            if urls is None:
                index[word] = {url}
            else:
                urls.add(url)
    return index
