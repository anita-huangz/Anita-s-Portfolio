"""The hand and its scoring.

Scoring is where the original was wrong twice, both times because it asked
whether an exact count was present rather than whether a threshold was met.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from enum import StrEnum

from .cards import Card

HAND_SIZE = 7
MAX_DISCARDS = 5


class HandRank(StrEnum):
    FOUR_KIND = "4Kind"
    FULL_HOUSE = "FullHouse"
    FLUSH = "Flush"
    THREE_KIND = "3Kind"
    TWO_PAIR = "2Pair"
    PAIR = "Pair"
    NOTHING = "None"


HAND_SCORES: dict[HandRank, int] = {
    HandRank.FOUR_KIND: 2000,
    HandRank.FULL_HOUSE: 250,
    HandRank.FLUSH: 200,
    HandRank.THREE_KIND: 100,
    HandRank.TWO_PAIR: 50,
    HandRank.PAIR: 10,
    HandRank.NOTHING: 0,
}


def score_cards(cards: list[Card]) -> HandRank:
    """Best rank the cards make.

    Two bugs the original had, both from testing for an exact count in a
    seven-card hand where five-card poker intuitions do not hold:

      * `5 in suit_counts.values()` misses a six- or seven-card flush, so the
        best flushes scored as nothing.
      * Full house was `3 in ranks and 2 in ranks`, which misses two separate
        three-of-a-kinds -- 3+3 is a full house, using three of one rank and a
        pair from the other.
    """
    if not cards:
        return HandRank.NOTHING

    rank_counts = Counter(card.rank for card in cards)
    suit_counts = Counter(card.suit for card in cards)
    # Sorted descending: how big the biggest group is, then the next.
    groups = sorted(rank_counts.values(), reverse=True)

    if groups[0] >= 4:
        return HandRank.FOUR_KIND

    # A second group of two *or more* completes the house: a second triple
    # contributes a pair.
    if groups[0] >= 3 and len(groups) > 1 and groups[1] >= 2:
        return HandRank.FULL_HOUSE

    if max(suit_counts.values()) >= 5:
        return HandRank.FLUSH

    if groups[0] >= 3:
        return HandRank.THREE_KIND

    if sum(1 for count in groups if count >= 2) >= 2:
        return HandRank.TWO_PAIR

    if groups[0] >= 2:
        return HandRank.PAIR

    return HandRank.NOTHING


@dataclass
class Hand:
    cards: list[Card] = field(default_factory=list)

    def __len__(self) -> int:
        return len(self.cards)

    def add(self, card: Card) -> None:
        self.cards.append(card)

    def reset(self) -> None:
        self.cards.clear()

    def discard(self, positions: set[int]) -> list[Card]:
        """Remove cards at the given zero-based positions and return them.

        Rejects an out-of-range position instead of ignoring it: silently
        dropping a bad index makes a mis-parsed prompt look like a discard the
        player did not ask for.
        """
        if len(positions) > MAX_DISCARDS:
            raise ValueError(f"at most {MAX_DISCARDS} cards may be discarded")
        out_of_range = {p for p in positions if not 0 <= p < len(self.cards)}
        if out_of_range:
            raise IndexError(f"no card at position(s) {sorted(out_of_range)}")

        removed = [card for i, card in enumerate(self.cards) if i in positions]
        self.cards = [card for i, card in enumerate(self.cards) if i not in positions]
        return removed

    def score(self) -> HandRank:
        return score_cards(self.cards)

    @property
    def points(self) -> int:
        return HAND_SCORES[self.score()]
