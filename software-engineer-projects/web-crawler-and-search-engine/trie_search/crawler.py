from utils import get_links, get_text, fetch_html, FetchException
# from collections import defaultdict
from trie import Trie

def crawl_site(start_url: str, max_depth: int) -> dict[str, list[str]]:
    """
    Given a starting URL, return a mapping of URLs mapped to words that appeared on that page.

    Important: In addition to following max_depth rule, pages must not be visited twice
    from a single call to crawl_site.

    Parameters:

        start_url - URL of page to start crawl on.
        max_depth - Maximum link depth into site to visit.
                    Links from the start page would be depth=1, links from those depth=2, and so on.

    Returns:
        Dictionary mapping strings to lists of strings.

        Dictionary keys: URLs of pages visited.
        Dictionary values: lists of all words that appeared on a given page.
    """

    results = {}
    visited = set()
    depth_map = {start_url: 0}
    urls = [start_url]

    while urls:
        current_url = urls.pop(0)
        current_depth = depth_map[current_url]

        try:
            # Fetch HTML and extract text
            html = fetch_html(current_url)
            words = get_text(html).split()
            results[current_url] = words

            # Extract and process links only if within depth limits
            if current_depth < max_depth:
                links = get_links(html, current_url)
                for link in links:
                    if link not in visited:
                        visited.add(link)
                        urls.append(link)
                        depth_map[link] = current_depth + 1

        except FetchException as e:
            continue

    return results


def build_index(site_url: str, max_depth: int) -> Trie:
    """
    Given a starting URL, build a `Trie` of all words seen mapped to
    the page(s) they appeared upon.

    Parameters:

        start_url - URL of page to start crawl on.
        max_depth - Maximum link depth into site to visit.

    Returns:
        `Trie` where the keys are words seen on the crawl, and the
        value associated with each key is a set of URLs that word
        appeared on.
    """
    # Initialize the Trie
    word_trie = Trie()

    # Get crawl results (URL -> list of words)
    crawl_results = crawl_site(site_url, max_depth)

    # Populate the Trie with words and their associated URLs
    for url, words in crawl_results.items():
        for word in words:
            if word not in word_trie:
                word_trie[word] = set()  # Initialize a set for the word
            word_trie[word].add(url)  # Add the URL to the word's set

    return word_trie  # Return the constructed Trie
