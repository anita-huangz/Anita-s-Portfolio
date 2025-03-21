from rich.console import Console
from rich.table import Table
from rich.prompt import Prompt
from crawler import build_index


def display_results(word: str, urls: set):
    """
    Display search results for a word in a table format using `rich`.

    Parameters:
        word - The searched word.
        urls - The set of URLs where the word was found.
    """
    console = Console()

    # Create a table with two columns
    table = Table(title=f"Search Results for '{word}'")
    table.add_column("Word", justify="right", style="cyan", no_wrap=True)
    table.add_column("URL(s)", style="magenta")

    # Add rows to the table
    for url in urls:
        table.add_row(word, url)

    # Print the table
    console.print(table)


def search_interface(trie):
    """
    Launch an interactive search interface.

    Parameters:
        trie - The Trie containing the indexed data.
    """
    console = Console()
    console.print("[bold blue]Search Interface[/bold blue]\n", style="bold")

    while True:
        # Prompt the user for input
        query = Prompt.ask("[bold magenta]Enter a word to search (or 'exit' to quit)[/bold magenta]").strip()
        if query.lower() == "exit":
            console.print("[bold yellow]Exiting search...[/bold yellow]")
            break

        # Search for the word in the Trie
        try:
            urls = trie[query]
            display_results(query, urls)
        except KeyError:
            console.print(f"[bold red]No results found for:[/bold red] {query}")


def main():
    """
    Main function to handle the full interface.

    1. Crawl the site.
    2. Build the search index (Trie).
    3. Launch the search interface.
    """
    console = Console()

    # Prompt for input URL and depth
    console.print("[bold blue]Welcome to the Web Crawler and Search Interface![/bold blue]")
    site_url = Prompt.ask("[bold green]Enter the URL to start crawling[/bold green]")
    max_depth = Prompt.ask("[bold green]Enter the maximum depth for crawling[/bold green]")

    # Validate depth input
    try:
        max_depth = int(max_depth)
    except ValueError:
        console.print("[bold red]Invalid depth value! Defaulting to 1.[/bold red]")
        max_depth = 1

    # Build the Trie index
    console.print(f"[bold yellow]Crawling {site_url} with depth {max_depth}...[/bold yellow]")

    trie = build_index(site_url, max_depth)
    console.print("[bold green]Crawling complete![/bold green]")

    # Launch the search interface
    search_interface(trie)


if __name__ == "__main__":
    main()
