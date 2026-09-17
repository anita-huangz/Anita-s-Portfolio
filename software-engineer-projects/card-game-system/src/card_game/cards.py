"""Cards and the deck."""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from enum import StrEnum

RANKS: tuple[str, ...] = (
    "2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K", "A",
)


class Suit(StrEnum):
    CLUBS = "clubs"
    DIAMONDS = "diamonds"
    HEARTS = "hearts"
    SPADES = "spades"

    @property
    def symbol(self) -> str:
        return {"clubs": "♣", "diamonds": "♦", "hearts": "♥", "spades": "♠"}[self.value]

    @property
    def color(self) -> str:
        return "black" if self in (Suit.CLUBS, Suit.SPADES) else "red"


@dataclass(frozen=True)
class Card:
    suit: Suit
    rank: str

    def __post_init__(self) -> None:
        if self.rank not in RANKS:
            raise ValueError(f"not a valid rank: {self.rank!r}")

    @property
    def color(self) -> str:
        return self.suit.color

    def __str__(self) -> str:
        return f"{self.rank}{self.suit.symbol}"


class OutOfCards(RuntimeError):
    """The deck was asked for a card it does not have."""


@dataclass
class Deck:
    """A 52-card deck that deals from the top and recycles discards.

    Dealing raises rather than returning None. The previous version returned
    None and printed a message, so an exhausted deck put a None into the
    player's hand and crashed later in scoring, far from the cause.
    """

    cards: list[Card] = field(default_factory=list)
    dealt: list[Card] = field(default_factory=list)
    _rng: random.Random = field(default_factory=random.Random, repr=False)

    def __init__(self, seed: int | None = None) -> None:
        # Seedable so a game is reproducible in a test.
        self._rng = random.Random(seed)
        self.cards = [Card(suit, rank) for suit in Suit for rank in RANKS]
        self.dealt = []
        self.shuffle()

    def __len__(self) -> int:
        return len(self.cards)

    def shuffle(self) -> None:
        """Shuffle the undealt cards."""
        self._rng.shuffle(self.cards)

    def recycle(self) -> None:
        """Shuffle the discards and put them under the remaining deck."""
        self._rng.shuffle(self.dealt)
        self.cards.extend(self.dealt)
        self.dealt.clear()

    def deal(self) -> Card:
        if not self.cards:
            raise OutOfCards("the deck is empty")
        card = self.cards.pop(0)
        self.dealt.append(card)
        return card

    def deal_many(self, count: int) -> list[Card]:
        if count > len(self.cards):
            raise OutOfCards(f"asked for {count} cards, {len(self.cards)} remain")
        return [self.deal() for _ in range(count)]
