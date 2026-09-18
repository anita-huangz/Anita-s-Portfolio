"""The hand and its scoring.

Scoring is where the original was wrong twice, both times because it asked
whether an exact count was present rather than whether a threshold was met.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from enum import StrEnum

from .cards import RANKS, Card

HAND_SIZE = 7
MAX_DISCARDS = 5

#: Comparable values for the ranks, aces high. The ace's second, low value is
#: handled in `straight_high` rather than here, because a rank cannot hold two
#: values at once and pretending otherwise is how the wheel gets lost.
RANK_VALUES: dict[str, int] = {rank: i for i, rank in enumerate(RANKS, start=2)}
VALUE_RANKS: dict[int, str] = {v: k for k, v in RANK_VALUES.items()}

ACE_VALUE = RANK_VALUES["A"]
#: The ace's low value, for A-2-3-4-5. Below the deuce, hence 1.
ACE_LOW = 1

STRAIGHT_LENGTH = 5


class HandRank(StrEnum):
    STRAIGHT_FLUSH = "StraightFlush"
    FOUR_KIND = "4Kind"
    FULL_HOUSE = "FullHouse"
    FLUSH = "Flush"
    STRAIGHT = "Straight"
    THREE_KIND = "3Kind"
    TWO_PAIR = "2Pair"
    PAIR = "Pair"
    NOTHING = "None"


HAND_SCORES: dict[HandRank, int] = {
    HandRank.STRAIGHT_FLUSH: 5000,
    HandRank.FOUR_KIND: 2000,
    HandRank.FULL_HOUSE: 250,
    HandRank.FLUSH: 200,
    HandRank.STRAIGHT: 150,
    HandRank.THREE_KIND: 100,
    HandRank.TWO_PAIR: 50,
    HandRank.PAIR: 10,
    HandRank.NOTHING: 0,
}


def straight_high(cards: list[Card]) -> str | None:
    """Highest card of the best straight in `cards`, or None if there is none.

    Two things make this more than a sort-and-scan.

    **Seven cards, not five.** A straight only needs five *consecutive*
    ranks somewhere in the hand, so duplicates have to be collapsed first --
    otherwise a pair inside the run breaks the sequence check.

    **The ace counts twice.** A-2-3-4-5 is a straight (the "wheel") and so is
    10-J-Q-K-A, and an ace cannot hold both values at once. The ace is
    therefore added at *both* ends of the value set. Ranking by value alone
    would make the wheel the highest straight in the deck rather than the
    lowest, so the wheel reports its high card as the 5.
    """
    values = {RANK_VALUES[card.rank] for card in cards}
    if ACE_VALUE in values:
        values.add(ACE_LOW)

    best: int | None = None
    for high in sorted(values, reverse=True):
        if all(high - offset in values for offset in range(STRAIGHT_LENGTH)):
            best = high
            break
    if best is None:
        return None
    # A straight's high value is at least 5, so the ace's low value is never
    # the answer here: the wheel reports the 5 it runs up to, which is also
    # what makes it rank below every other straight.
    return VALUE_RANKS[best]


def straight_flush_high(cards: list[Card]) -> str | None:
    """Highest card of the best straight flush, or None.

    Checked per suit, which is the point. "Has a straight and has a flush" is
    not the same question: seven cards can easily hold a straight in mixed
    suits *and* five cards of one suit that are not consecutive, and that hand
    is not a straight flush. Only cards of a single suit can form one.
    """
    by_suit: dict[object, list[Card]] = {}
    for card in cards:
        by_suit.setdefault(card.suit, []).append(card)

    best_value: int | None = None
    best_rank: str | None = None
    for suited in by_suit.values():
        if len(suited) < STRAIGHT_LENGTH:
            continue
        high = straight_high(suited)
        if high is None:
            continue
        # Compare on value, but a wheel's reported high is the 5.
        value = RANK_VALUES[high]
        if best_value is None or value > best_value:
            best_value, best_rank = value, high
    return best_rank


def score_cards(cards: list[Card]) -> HandRank:
    """Best rank the cards make.

    Two bugs the original had, both from testing for an exact count in a
    seven-card hand where five-card poker intuitions do not hold:

      * `5 in suit_counts.values()` misses a six- or seven-card flush, so the
        best flushes scored as nothing.
      * Full house was `3 in ranks and 2 in ranks`, which misses two separate
        three-of-a-kinds -- 3+3 is a full house, using three of one rank and a
        pair from the other.

    Straights and straight flushes were missing entirely, which in a
    seven-card game is not a small omission: a straight is more likely than a
    flush, so hands that should have scored were scoring as nothing and ending
    the game.
    """
    if not cards:
        return HandRank.NOTHING

    rank_counts = Counter(card.rank for card in cards)
    suit_counts = Counter(card.suit for card in cards)
    # Sorted descending: how big the biggest group is, then the next.
    groups = sorted(rank_counts.values(), reverse=True)

    if straight_flush_high(cards) is not None:
        return HandRank.STRAIGHT_FLUSH

    if groups[0] >= 4:
        return HandRank.FOUR_KIND

    # A second group of two *or more* completes the house: a second triple
    # contributes a pair.
    if groups[0] >= 3 and len(groups) > 1 and groups[1] >= 2:
        return HandRank.FULL_HOUSE

    if max(suit_counts.values()) >= 5:
        return HandRank.FLUSH

    if straight_high(cards) is not None:
        return HandRank.STRAIGHT

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
