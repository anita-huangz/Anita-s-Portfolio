"""Entry point: the loop that wires prompts to game state."""

from __future__ import annotations

import argparse

from rich import print as rprint
from rich.prompt import Confirm

from .cards import Deck
from .display import prompt_for_discards, show_game_state
from .game import Game


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="A single-player poker-style draw game.")
    parser.add_argument("--seed", type=int, default=None, help="Seed the shuffle.")
    args = parser.parse_args(argv)

    game = Game(deck=Deck(seed=args.seed))

    while not game.over:
        game.deal_round()
        show_game_state(game)

        game.apply_discards(prompt_for_discards())
        show_game_state(game)

        rank = game.finish_round()
        show_game_state(game)

        if game.over:
            break
        if not Confirm.ask(f"Scored {rank.value}. Next round?"):
            break

    rprint(f"\nGame over after {len(game.round_scores)} scoring round(s).")
    rprint(f"Final score: [bold]{game.total_score}[/bold]")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
