"""HTTP fetching and HTML extraction.

The previous version kept the set of visited URLs in a module-level global, so
a second crawl in the same process failed on every URL it had already seen. The
visited set now belongs to the crawl.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import httpx
import lxml.html

DEFAULT_ALLOWED = ("https://example.com", "https://scrapple.fly.dev")


class FetchError(Exception):
    """A page could not be fetched, or was not allowed to be."""


@dataclass
class Fetcher:
    """Fetches pages, restricted to an allowlist of URL prefixes.

    The allowlist is a guardrail, not a security boundary: it keeps a crawl
    from wandering off a test site. It does not make crawling arbitrary hosts
    safe or polite.
    """

    allowed_prefixes: tuple[str, ...] = DEFAULT_ALLOWED
    timeout: float = 10.0
    client: httpx.Client | None = field(default=None, repr=False)

    def is_allowed(self, url: str) -> bool:
        return url.startswith("https://") and url.startswith(self.allowed_prefixes)

    def fetch(self, url: str) -> str:
        if not url.startswith("https://"):
            raise FetchError(f"{url} must start with https://")
        if not url.startswith(self.allowed_prefixes):
            raise FetchError(f"{url} is outside the allowed prefixes")

        client = self.client or httpx.Client(timeout=self.timeout, follow_redirects=True)
        try:
            response = client.get(url)
            response.raise_for_status()
            return response.text
        except httpx.HTTPError as exc:
            raise FetchError(f"fetching {url} failed: {exc}") from exc
        finally:
            if self.client is None:
                client.close()


def get_links(html: str, source_url: str) -> list[str]:
    """Absolute URLs of every anchor on the page."""
    doc = lxml.html.fromstring(html)
    doc.make_links_absolute(source_url)
    return [str(href) for href in doc.xpath("//a/@href")]


def get_text(html: str) -> str:
    """Visible text, with script and style content removed.

    Two things `text_content()` gets wrong for indexing:

      * it includes the body of `<script>` and `<style>`, so a page's
        JavaScript ends up indexed as searchable words;
      * it concatenates adjacent elements with no separator, so
        `<a>C</a><p>alpha</p>` becomes "Calpha" and neither word is findable.

    Joining the text nodes with a space fixes the second.
    """
    doc = lxml.html.fromstring(html)
    for element in doc.xpath("//script | //style"):
        element.drop_tree()
    return " ".join(chunk.strip() for chunk in doc.itertext() if chunk.strip())


#: Stripped from the ends of a token. Internal punctuation is kept, so
#: "well-known" stays one word while a bare "--" is dropped entirely.
PUNCTUATION = ".,;:!?()[]{}<>\"'`\u2014\u2013-_*|/\\"


def tokenize(text: str) -> list[str]:
    """Split text into lowercase words, dropping punctuation-only tokens."""
    words = []
    for raw in text.split():
        word = raw.strip(PUNCTUATION).lower()
        if word:
            words.append(word)
    return words
