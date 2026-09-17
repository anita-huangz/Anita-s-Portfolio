"""Crawl a site, then search the index from the terminal."""

from __future__ import annotations

import argparse
import sys

from rich.console import Console
from rich.prompt import Prompt
from rich.table import Table

from .crawler import build_index, crawl_site, index_pages
from .fetch import Fetcher
from .trie import Trie

console = Console()


def show_results(query: str, matches: list[tuple[str, set[str]]]) -> None:
    if not matches:
        console.print(f"[yellow]No matches for {query!r}.[/yellow]")
        return

    table = Table(title=f"Results for {query!r}")
    table.add_column("Word", style="cyan", no_wrap=True)
    table.add_column("Pages", justify="right", style="green")
    table.add_column("URL(s)", style="magenta")

    for word, urls in matches:
        table.add_row(word, str(len(urls)), "\n".join(sorted(urls)))
    console.print(table)


def search(index: Trie, query: str) -> list[tuple[str, set[str]]]:
    """Wildcard search when the query contains '?', otherwise prefix search."""
    query = query.strip().lower()
    if not query:
        return []
    if "?" in query:
        return sorted(index.wildcard_search(query))
    return sorted((word, index[word]) for word in index.keys_with_prefix(query))


def interactive(index: Trie) -> None:
    console.print("[bold blue]Search[/bold blue]  ('?' is a single-character wildcard, "
                  "blank to quit)\n")
    while True:
        query = Prompt.ask("query", default="").strip()
        if not query:
            break
        show_results(query, search(index, query))


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

    index = index_pages(result.pages)
    console.print(f"Indexed [bold]{len(index):,}[/bold] distinct words.\n")

    if args.query:
        show_results(args.query, search(index, args.query))
    else:
        interactive(index)
    return 0


__all__ = ["build_index", "main", "search"]


if __name__ == "__main__":
    sys.exit(main())
