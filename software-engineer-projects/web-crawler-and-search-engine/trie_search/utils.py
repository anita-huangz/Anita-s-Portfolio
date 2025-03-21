import httpx
import lxml.html

ALLOWED_DOMAINS = ("https://example.com", "https://scrapple.fly.dev/parks")


class FetchException(Exception):
    pass


_seen_already = set()


def fetch_html(url: str) -> str:
    """
    Fetch HTML from a given URL.

    Parameters:
        url -

    Returns:
        String containing HTML from the page.
    """
    if url in _seen_already:
        raise FetchException(
            f"URL {url} already seen this run, exiting to avoid infinite loops."
        )
    _seen_already.add(url)
    if not url.startswith("https://"):
        raise FetchException(f"URL {url} must start with https://")
    elif not url.startswith(ALLOWED_DOMAINS):
        raise FetchException(f"URL {url} does not start with an allowed domain")
    try:
        return httpx.get(url).text
    except Exception as e:
        raise FetchException(str(e))


def get_links(html: str, source_url: str) -> list[str]:
    """
    Get all URLs that are on a given page.

    Parameters:
        html - Page HTML.
        source_url - URL of source page.

    Returns:
        List of URLs that appeared on page.
    """
    doc = lxml.html.fromstring(html)
    doc.make_links_absolute(source_url)
    return doc.xpath("//a/@href")


def get_text(html: str) -> str:
    """
    Get all text on a given page.

    Parameters:
        html - Page HTML.

    Returns:
        Text extracted from the page.
    """
    return lxml.html.fromstring(html).text_content()
