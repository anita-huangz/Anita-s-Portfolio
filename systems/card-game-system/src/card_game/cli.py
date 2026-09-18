"""Entry point: the loop that wires prompts to game state."""

from __future__ import annotations

import argparse

from rich import print as rprint
from rich.prompt import Confirm

from .advisor import DEFAULT_TRIALS, advise
from .cards import Deck, parse_hand
from .display import prompt_for_discards, show_game_state
from .game import Game


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="A single-player poker-style draw game.")
    parser.add_argument("--seed", type=int, default=None, help="Seed the shuffle.")
    parser.add_argument(
        "--advise",
        metavar="HAND",
        help='Analyse a hand and exit, e.g. --advise "Ah Kh 9h 4h 7c 7s 2d".',
    )
    parser.add_argument(
        "--hints",
        action="store_true",
        help="Show the best discards before each prompt.",
    )
    parser.add_argument(
        "--trials",
        type=int,
        default=DEFAULT_TRIALS,
        help="Samples per discard where exact enumeration is too expensive.",
    )
    args = parser.parse_args(argv)

    if args.advise:
        try:
            hand = parse_hand(args.advise)
        except ValueError as exc:
            rprint(f"[red]error:[/red] {exc}")
            return 2
        rprint(advise(hand, trials=args.trials))
        return 0

    game = Game(deck=Deck(seed=args.seed))

    while not game.over:
        game.deal_round()
        show_game_state(game)

        if args.hints:
            rprint(advise(game.hand.cards, trials=args.trials, top=3))

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
