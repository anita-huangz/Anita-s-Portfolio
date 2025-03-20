from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich.prompt import Prompt
from rich import print
from card import Card
from deck import Deck
from hand import Hand, HAND_SCORES


def _card_to_display(card: Card):
    """
    Helper method to draw a single card.

    (Do not call directly!)
    """
    return Panel(
        Text(f"{card}\n\n{str(card):>3}", style=card.color()),
        width=7,
        height=5,
        style="black on white",
    )


def _hand_to_display(hand: Hand):
    """
    Helper method to draw a hand.

    (Do not call directly!)
    """


def show_game_state(
    *,
    deck: Deck,
    hand: Hand,
    round_scores: list[int],
):
    """
    Method to draw the current state of the game.

    Each of these parameters should be defined within `main` in main.py and passed to this function.

    Parameters:
        deck:         Deck of cards.
        hand:         Player's Hand.
        round_scores: A list of scores for each round.
                      Empty in first round, and increasing in size each round.
    """
    # clear screen
    print("\n" * 100)
    layout = Table.grid(expand=True)
    layout.add_column(ratio=2)
    layout.add_column(ratio=1)
    g = Table.grid("Player")
    for _ in hand.cards:
        g.add_column()
    g.add_row(*[_card_to_display(card) for card in hand.cards])
    g.add_row(*[f" ({i})" for i in range(1, 8)])
    score_text = "\n".join(
        [
            f"Round {n+1}: {score} {HAND_SCORES[score]}"
            for n, score in enumerate(round_scores)
        ]
    )
    total_score = sum(HAND_SCORES[score] for score in round_scores)
    layout.add_row(
        Panel(g),
        Panel(
            score_text
            + f"\n------\nTotal Score: {total_score}\n"
            + f"Round: {len(round_scores) + 1}\nCards Left: {len(deck)}",
            style="purple on white",
        ),
    )
    print(layout)


def prompt_for_discards():
    """
    Prompts player for which cards they would like to discard.

    The user will enter numbers 1-7 in any format. (e.g. the user may type 123 or 1,2,3)

    Those numbers will then be returned as a set of integers with one subtracted.
    Input "123" would become {0, 1, 2}.

    This behavior is so users can use natural numbers, and we can use array indices.

    Returns:
        set[int] of numbers to discard
    """
    response = Prompt.ask(
        "You may discard up to 5 cards.\nEnter their numbers all on one line (ex. '1 2 4')"
    )
    number_mapping = {str(i + 1): i for i in range(7)}
    discards = set()
    for ch in response:
        card = number_mapping.get(ch)
        if card is not None:
            discards.add(card)
    return discards
