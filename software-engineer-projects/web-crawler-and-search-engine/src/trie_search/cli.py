"""Crawl a site, then search the index from the terminal."""

from __future__ import annotations

import argparse
import sys

from rich.console import Console
from rich.prompt import Prompt
from rich.table import Table

from .crawler import SearchIndex, build_index, build_search_index, crawl_site
from .fetch import Fetcher
from .ranking import Hit
from .trie import Trie

console = Console()


def show_results(query: str, hits: list[Hit]) -> None:
    """Ranked results, best first, each explaining why it matched."""
    if not hits:
        console.print(f"[yellow]No matches for {query!r}.[/yellow]")
        return

    table = Table(title=f"Results for {query!r}")
    table.add_column("#", justify="right", style="dim")
    table.add_column("Score", justify="right", style="green")
    table.add_column("Page", style="magenta")
    table.add_column("Matched", style="cyan")

    for position, hit in enumerate(hits, 1):
        terms = ", ".join(
            f"{term} x{count}" for term, count in sorted(hit.matched.items())
        )
        table.add_row(str(position), f"{hit.score:.3f}", hit.url, terms)
    console.print(table)


def search(index: Trie, query: str) -> list[tuple[str, set[str]]]:
    """Unranked lookup over a set-valued index.

    Retained because it is the simplest thing that answers "which pages
    contain this word". `SearchIndex.search` is what the CLI uses -- a result
    list with no ordering is not much use once there is more than a handful.
    """
    query = query.strip().lower()
    if not query:
        return []
    if "?" in query:
        return sorted(index.wildcard_search(query))
    return sorted((word, index[word]) for word in index.keys_with_prefix(query))


def interactive(index: SearchIndex) -> None:
    console.print(
        "[bold blue]Search[/bold blue]  (space-separated words are ANDed, "
        "'?' matches one character, trailing '*' matches a prefix; blank to quit)\n"
    )
    while True:
        query = Prompt.ask("query", default="").strip()
        if not query:
            break
        show_results(query, index.search(query))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Crawl a site and search it with a trie-backed index."
    )
    parser.add_argument("url", help="URL to start the crawl from.")
    parser.add_argument("--depth", type=int, default=1, help="Link depth to follow.")
    parser.add_argument("--query", help="Search and exit instead of prompting.")
    parser.add_argument(
        "--allow",
        default=None,
        help="Comma-separated URL prefixes the crawl may visit (default: the start URL).",
    )
    args = parser.parse_args(argv)

    prefixes = (
        tuple(p.strip() for p in args.allow.split(",") if p.strip())
        if args.allow
        else (args.url,)
    )
    fetcher = Fetcher(allowed_prefixes=prefixes)

    with console.status(f"Crawling {args.url} to depth {args.depth}…"):
        result = crawl_site(args.url, args.depth, fetcher)

    console.print(
        f"Crawled [bold]{len(result.pages)}[/bold] page(s), "
        f"{result.word_count:,} words."
    )
    if result.failures:
        console.print(f"[yellow]{len(result.failures)} page(s) could not be fetched:[/yellow]")
        for url, reason in list(result.failures.items())[:5]:
            console.print(f"  {url} — {reason}")

    if not result.pages:
        console.print("[red]Nothing was indexed.[/red]")
        return 1

    index = build_search_index(result.pages)
    console.print(
        f"Indexed [bold]{len(index):,}[/bold] distinct words across "
        f"{index.pages} page(s), ranked with BM25.\n"
    )

    if args.query:
        show_results(args.query, index.search(args.query))
    else:
        interactive(index)
    return 0


__all__ = ["build_index", "main", "search"]


if __name__ == "__main__":
    sys.exit(main())
