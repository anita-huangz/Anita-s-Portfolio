"""The search command line, driven against a fake fetcher.

It was 32% covered — the argument parsing ran in tests, the crawl and render
path never did. No test here touches the network: `Fetcher` takes an injected
client, which is the seam that makes an offline test of the real code possible.
"""

import httpx
import pytest

from trie_search.cli import main

PAGES = {
    "https://example.com/": (
        '<html><body><h1>Park directory</h1>'
        '<p>Every park in the city. Park hours are posted.</p>'
        '<a href="https://example.com/dogs">dogs</a></body></html>'
    ),
    "https://example.com/dogs": (
        "<html><body><p>Dog park rules. Dogs must be leashed outside the "
        "designated dog park area.</p></body></html>"
    ),
}


@pytest.fixture
def offline(monkeypatch):
    """Serve the pages above instead of reaching the internet."""

    def handler(request: httpx.Request) -> httpx.Response:
        body = PAGES.get(str(request.url))
        if body is None:
            return httpx.Response(404, text="missing")
        return httpx.Response(200, text=body)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    import trie_search.cli as cli_module

    real = cli_module.Fetcher

    def fetcher(*args, **kwargs):
        kwargs["client"] = client
        return real(*args, **kwargs)

    monkeypatch.setattr(cli_module, "Fetcher", fetcher)
    return client


class TestSearch:
    def test_it_crawls_and_answers_a_query(self, offline, capsys):
        assert main(["https://example.com/", "--depth", "1", "--query", "park"]) == 0
        out = capsys.readouterr().out
        assert "Crawled" in out
        assert "example.com" in out

    def test_it_follows_links_to_the_requested_depth(self, offline, capsys):
        main(["https://example.com/", "--depth", "0", "--query", "dog"])
        shallow = capsys.readouterr().out
        main(["https://example.com/", "--depth", "1", "--query", "dog"])
        deep = capsys.readouterr().out
        assert "1 page(s)" in shallow
        assert "2 page(s)" in deep

    def test_a_phrase_query_runs(self, offline, capsys):
        assert main([
            "https://example.com/", "--depth", "1", "--query", '"dog park"',
        ]) == 0
        assert capsys.readouterr().out.strip()

    def test_stemming_is_announced_when_on(self, offline, capsys):
        assert main([
            "https://example.com/", "--depth", "1", "--stem", "--query", "parks",
        ]) == 0
        out = capsys.readouterr().out
        assert "stem" in out.lower()

    def test_without_positions_it_says_phrase_search_is_off(self, offline, capsys):
        assert main([
            "https://example.com/", "--depth", "0", "--no-positions",
            "--query", "park",
        ]) == 0
        assert "no phrase search" in capsys.readouterr().out

    def test_a_query_matching_nothing_still_exits_zero(self, offline, capsys):
        assert main([
            "https://example.com/", "--depth", "0", "--query", "zebra",
        ]) == 0
        assert capsys.readouterr().out.strip()


class TestFailures:
    def test_a_site_that_cannot_be_fetched_is_reported(self, offline, capsys):
        assert main([
            "https://example.com/missing", "--depth", "0", "--query", "park",
        ]) == 1
        combined = capsys.readouterr()
        assert "nothing was indexed" in (combined.out + combined.err).lower()

    def test_help_exits_cleanly(self):
        with pytest.raises(SystemExit) as exit:
            main(["--help"])
        assert exit.value.code == 0
