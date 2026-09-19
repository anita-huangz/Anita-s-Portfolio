"""Breadth-first crawl and index construction."""

from __future__ import annotations

from collections import Counter, deque
from dataclasses import dataclass, field

from .fetch import Fetcher, FetchError, get_links, get_text, tokenize
from .ranking import (
    Corpus,
    Hit,
    MissingPositions,
    Posting,
    rank,
    rank_phrase,
)
from .stem import stem
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
    """Build the word -> {urls} index from already-crawled pages.

    Kept for callers that only need membership. `build_search_index` is the
    one to use for ranked search, since a set cannot express how often a term
    occurs and BM25 needs exactly that.
    """
    index: Trie = Trie()
    for url, words in pages.items():
        for word in words:
            urls = index.get(word)
            if urls is None:
                index[word] = {url}
            else:
                urls.add(url)
    return index


@dataclass
class SearchIndex:
    """A ranked index: the trie for lookup, the corpus for scoring.

    The trie answers "which words look like this". The corpus answers "how
    important is this word on this page". Neither substitutes for the other.
    """

    trie: Trie = field(default_factory=Trie)
    corpus: Corpus = field(default_factory=Corpus)
    #: Whether occurrence offsets were recorded, and so whether phrase search
    #: is available. Stated up front so a phrase query can fail with a reason
    #: instead of quietly returning nothing.
    has_positions: bool = False
    #: Whether terms were reduced to Porter stems. The query has to be folded
    #: the same way or it will look up a surface form the index does not hold,
    #: so this travels with the index rather than being passed per search.
    stemmed: bool = False

    def __len__(self) -> int:
        return len(self.trie)

    @property
    def pages(self) -> int:
        return self.corpus.size

    def posting(self, term: str) -> Posting | None:
        value = self.trie.get(term)
        return value if isinstance(value, Posting) else None

    def expand(self, token: str) -> dict[str, Posting]:
        """Resolve one query token into the concrete terms it matches.

        A bare word is exact, `?` is a single-character wildcard, and a
        trailing `*` is a prefix. Expansion happens here so the scorer only
        ever sees real terms.
        """
        token = token.strip().lower()
        if not token:
            return {}

        # A stemmed index holds roots, so the query has to be a root too.
        # Wildcards are left alone: `par*` is a pattern over the stored keys,
        # and stemming a pattern would mangle it.
        if self.stemmed and "?" not in token and not token.endswith("*"):
            token = stem(token)

        if "?" in token:
            return {
                term: posting
                for term, posting in self.trie.wildcard_search(token)
                if isinstance(posting, Posting)
            }
        if token.endswith("*"):
            found: dict[str, Posting] = {}
            for term in self.trie.keys_with_prefix(token[:-1]):
                posting = self.posting(term)
                if posting is not None:
                    found[term] = posting
            return found

        posting = self.posting(token)
        return {token: posting} if posting is not None else {}

    def search(
        self, query: str, require_all: bool = True, limit: int = 20
    ) -> list[Hit]:
        """Rank pages for a whitespace-separated query.

        `require_all` defaults to True: someone typing two words almost always
        means both, and an OR search buries the good hits under pages that only
        matched the commoner word.

        Double quotes make a phrase: `"park hours"` requires the words adjacent
        and in that order, where the unquoted form only requires both somewhere
        on the page.
        """
        phrase = _quoted(query)
        if phrase is not None:
            return self.search_phrase(phrase, limit=limit)

        tokens = [t for t in query.strip().lower().split() if t]
        if not tokens:
            return []

        postings: dict[str, Posting] = {}
        matched_tokens = 0
        for token in tokens:
            expanded = self.expand(token)
            if expanded:
                matched_tokens += 1
            postings.update(expanded)

        if require_all and matched_tokens < len(tokens):
            # A token nothing matches means the AND can never be satisfied.
            return []

        # A wildcard token expands to many terms, so requiring every *term* to
        # be present would be wrong; the intent is every *token*. The two only
        # coincide when each token resolved to exactly one term.
        strict = require_all and len(tokens) == len(postings)
        return rank(postings, self.corpus, require_all=strict)[:limit]

    def search_phrase(self, terms: list[str], limit: int = 20) -> list[Hit]:
        """Rank pages where these words appear adjacent and in order."""
        if not terms:
            return []
        if not self.has_positions:
            raise MissingPositions(
                "this index was built without positions, so phrase search is "
                "unavailable; rebuild with build_search_index(pages)"
            )
        if self.stemmed:
            terms = [stem(t) for t in terms]
        postings = []
        for term in terms:
            posting = self.posting(term)
            # One absent word means the phrase cannot occur. Falling back to a
            # bag-of-words search here would answer a question nobody asked.
            if posting is None:
                return []
            postings.append(posting)
        if len(postings) == 1:
            return rank({terms[0]: postings[0]}, self.corpus)[:limit]
        return rank_phrase(terms, postings, self.corpus)[:limit]


def _quoted(query: str) -> list[str] | None:
    """The words inside double quotes, or None if the query is not a phrase."""
    text = query.strip()
    if len(text) >= 2 and text[0] == text[-1] == '"':
        return [t for t in text[1:-1].lower().split() if t]
    return None


def build_search_index(
    pages: dict[str, list[str]], positions: bool = True, stemming: bool = False
) -> SearchIndex:
    """Build a ranked index: term frequencies per page, plus page lengths.

    `positions` also records where each occurrence sits, which is what phrase
    search needs. It costs memory proportional to the corpus rather than to the
    vocabulary -- every occurrence, not every distinct word -- so it is a real
    choice and not a free upgrade. `--no-positions` on the command line turns
    it off, and `trie-bench --index` measures what it costs.
    """
    index = SearchIndex(has_positions=positions, stemmed=stemming)
    for url, words in pages.items():
        index.corpus.add(url, len(words))
        if stemming:
            # Positions still refer to the original word order, so a phrase
            # query works on stems exactly as it does on surface forms.
            words = [stem(w) for w in words]
        if positions:
            offsets: dict[str, list[int]] = {}
            for offset, word in enumerate(words):
                offsets.setdefault(word, []).append(offset)
            for word, where in offsets.items():
                posting = index.posting(word)
                if posting is None:
                    posting = Posting()
                    index.trie[word] = posting
                posting.record(url, where)
        else:
            for word, count in Counter(words).items():
                posting = index.posting(word)
                if posting is None:
                    index.trie[word] = Posting(counts={url: count})
                else:
                    posting.counts[url] = count
    return index
