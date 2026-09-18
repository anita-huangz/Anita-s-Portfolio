"""Terminal rendering. The only module that knows about `rich`."""

from __future__ import annotations

from rich import print as rprint
from rich.panel import Panel
from rich.prompt import Prompt
from rich.table import Table
from rich.text import Text

from .cards import Card
from .game import Game
from .hand import HAND_SCORES, HAND_SIZE, MAX_DISCARDS, Hand


def render_card(card: Card) -> Panel:
    return Panel(
        Text(f"{card}\n\n{card!s:>3}", style=card.color),
        width=7,
        height=5,
        style="black on white",
    )


def render_hand(hand: Hand) -> Table:
    grid = Table.grid()
    for _ in hand.cards:
        grid.add_column()
    grid.add_row(*[render_card(card) for card in hand.cards])
    grid.add_row(*[f" ({i})" for i in range(1, len(hand.cards) + 1)])
    return grid


def render_scoreboard(game: Game) -> str:
    lines = [
        f"Round {n + 1}: {rank.value} {HAND_SCORES[rank]}"
        for n, rank in enumerate(game.round_scores)
    ]
    lines += [
        "------",
        f"Total Score: {game.total_score}",
        f"Round: {game.round_number}",
        f"Cards Left: {len(game.deck)}",
    ]
    return "\n".join(lines)


def show_game_state(game: Game) -> None:
    print("\n" * 100)  # clear screen
    layout = Table.grid(expand=True)
    layout.add_column(ratio=2)
    layout.add_column(ratio=1)
    layout.add_row(
        Panel(render_hand(game.hand)),
        Panel(render_scoreboard(game), style="purple on white"),
    )
    rprint(layout)


def parse_discards(response: str, hand_size: int = HAND_SIZE) -> set[int]:
    """Turn a free-form reply into zero-based positions.

    The player types natural numbers in any format -- "123", "1 2 3", "1,2,3".
    Digits outside the hand are ignored; the rest map to indices.
    """
    valid = {str(i + 1): i for i in range(hand_size)}
    return {valid[ch] for ch in response if ch in valid}


def prompt_for_discards(hand_size: int = HAND_SIZE) -> set[int]:
    while True:
        response = Prompt.ask(
            f"You may discard up to {MAX_DISCARDS} cards.\n"
            "Enter their numbers all on one line (ex. '1 2 4'), or press enter to keep all"
        )
        discards = parse_discards(response, hand_size)
        if len(discards) <= MAX_DISCARDS:
            return discards
        rprint(f"[red]At most {MAX_DISCARDS} cards -- you chose {len(discards)}.[/red]")
