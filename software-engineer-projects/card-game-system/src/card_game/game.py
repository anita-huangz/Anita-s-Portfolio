"""Game rules, with no terminal I/O.

Separating the rules from the display is what makes a full game playable in a
test: `Game` exposes the state transitions, and `cli.py` is the only thing that
prints or prompts.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .cards import Deck, OutOfCards
from .hand import HAND_SCORES, HAND_SIZE, Hand, HandRank


@dataclass
class Game:
    deck: Deck = field(default_factory=Deck)
    hand: Hand = field(default_factory=Hand)
    round_scores: list[HandRank] = field(default_factory=list)
    over: bool = False

    @property
    def total_score(self) -> int:
        return sum(HAND_SCORES[rank] for rank in self.round_scores)

    @property
    def round_number(self) -> int:
        return len(self.round_scores) + 1

    def deal_round(self) -> None:
        """Start a round with a fresh seven-card hand."""
        self.hand.reset()
        if len(self.deck) < HAND_SIZE:
            # Recycle rather than ending the game on an empty deck: the rules
            # are about failing to score, not about running out of cards.
            self.deck.recycle()
        self.hand.cards = self.deck.deal_many(HAND_SIZE)

    def apply_discards(self, positions: set[int]) -> None:
        """Discard the chosen cards and draw replacements."""
        if not positions:
            return
        self.hand.discard(positions)
        needed = HAND_SIZE - len(self.hand)
        if needed > len(self.deck):
            self.deck.recycle()
        try:
            for card in self.deck.deal_many(needed):
                self.hand.add(card)
        except OutOfCards:
            # Play on with a short hand rather than crashing mid-round.
            self.over = True

    def finish_round(self) -> HandRank:
        """Score the hand. A hand that does not score ends the game."""
        rank = self.hand.score()
        if rank is HandRank.NOTHING:
            self.over = True
        else:
            self.round_scores.append(rank)
        return rank
