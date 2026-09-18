"""A single-player poker-style draw game with a scored hand evaluator."""

from .advisor import (
    Outcome,
    advise,
    all_discards,
    best_discards,
    evaluate_discard,
    statistical_ties,
    unseen_cards,
)
from .cards import Card, Deck, OutOfCards, Suit, parse_card, parse_hand
from .game import Game
from .hand import (
    HAND_SCORES,
    Hand,
    HandRank,
    score_cards,
    straight_flush_high,
    straight_high,
)

__all__ = [
    "HAND_SCORES",
    "Card",
    "Deck",
    "Game",
    "Hand",
    "HandRank",
    "OutOfCards",
    "Outcome",
    "Suit",
    "advise",
    "all_discards",
    "best_discards",
    "evaluate_discard",
    "parse_card",
    "parse_hand",
    "score_cards",
    "statistical_ties",
    "straight_flush_high",
    "straight_high",
    "unseen_cards",
]

__version__ = "0.3.0"
