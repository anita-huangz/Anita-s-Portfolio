"""Which cards to throw away.

The game asked the player to choose discards and gave them nothing to choose
with. The choice is not obvious either: holding a pair and drawing five is a
completely different bet from holding four to a flush and drawing three, and
the better one depends on numbers nobody works out at the table.

This evaluates every legal discard -- all 120 of them for a seven-card hand
with at most five discards -- and reports the expected score of each.

**Exact where exact is affordable, sampled where it is not.** Discarding one
card has 45 possible replacements and discarding two has 990, so those answers
are computed by enumeration and are not estimates at all. Five discards has
1.2 million, so that one is sampled. The two are not interchangeable and the
output says which it used.

**Sampled numbers come with an error bar, and the advice respects it.** With
200 trials, two options whose expected scores differ by 15 points are not
distinguishable, and presenting them as ranked 1st and 2nd would be reporting
noise as a finding. `best_discards` marks every option that ties with the
leader inside the margin of error.
"""

from __future__ import annotations

import math
import random
from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from itertools import combinations

from .cards import RANKS, Card, Suit
from .hand import HAND_SCORES, MAX_DISCARDS, HandRank, score_cards

#: Enumerate rather than sample while the number of draws is at most this.
#: 990 covers a two-card discard exactly; three is 14,190 and is sampled.
EXACT_LIMIT = 1_000

DEFAULT_TRIALS = 400

#: Two sampled options are called a tie when their means are within this many
#: standard errors of each other.
TIE_SIGMAS = 2.0


def full_deck() -> list[Card]:
    return [Card(suit, rank) for suit in Suit for rank in RANKS]


def unseen_cards(known: Sequence[Card]) -> list[Card]:
    """Every card the player has not seen.

    The hand is the only information available -- there are no opponents and
    no exposed cards -- so the unseen set is the deck minus the hand. Drawing
    from a freshly shuffled deck that still contains the player's own cards
    would quietly overstate the chance of improving a pair.
    """
    held = set(known)
    return [card for card in full_deck() if card not in held]


@dataclass(frozen=True)
class Outcome:
    """What a given discard is worth."""

    positions: frozenset[int]
    expected_points: float
    #: Probability of each resulting rank, highest score first.
    distribution: dict[HandRank, float]
    draws: int
    exact: bool
    standard_error: float

    @property
    def discarded(self) -> int:
        return len(self.positions)

    @property
    def probability_of_scoring(self) -> float:
        """Chance of making anything at all. A round scoring nothing ends the game."""
        return 1.0 - self.distribution.get(HandRank.NOTHING, 0.0)

    def describe(self, hand: Sequence[Card]) -> str:
        cards = (
            ", ".join(str(hand[i]) for i in sorted(self.positions))
            if self.positions
            else "nothing"
        )
        kind = "exact" if self.exact else f"±{TIE_SIGMAS * self.standard_error:.0f}"
        return (
            f"discard {cards:<24} {self.expected_points:>7.1f} pts ({kind}), "
            f"scores {self.probability_of_scoring:>5.1%}"
        )


def _replacements(
    pool: Sequence[Card], count: int, trials: int, rng: random.Random
) -> tuple[Iterator[Sequence[Card]], int, bool]:
    """Draws to evaluate, how many, and whether they are exhaustive."""
    if count == 0:
        return iter([()]), 1, True
    total = math.comb(len(pool), count)
    if total <= EXACT_LIMIT:
        return combinations(pool, count), total, True
    return (
        (rng.sample(pool, count) for _ in range(trials)),
        trials,
        False,
    )


def evaluate_discard(
    hand: Sequence[Card],
    positions: frozenset[int] | set[int],
    *,
    trials: int = DEFAULT_TRIALS,
    rng: random.Random | None = None,
) -> Outcome:
    """Expected points from discarding `positions` and drawing replacements."""
    positions = frozenset(positions)
    bad = {p for p in positions if not 0 <= p < len(hand)}
    if bad:
        raise IndexError(f"no card at position(s) {sorted(bad)}")
    if len(positions) > MAX_DISCARDS:
        raise ValueError(f"at most {MAX_DISCARDS} cards may be discarded")

    rng = rng or random.Random(0)
    kept = [card for i, card in enumerate(hand) if i not in positions]
    pool = unseen_cards(hand)
    draws, count, exact = _replacements(pool, len(positions), trials, rng)

    tally: dict[HandRank, int] = {}
    total = 0.0
    total_squared = 0.0
    for drawn in draws:
        rank = score_cards([*kept, *drawn])
        tally[rank] = tally.get(rank, 0) + 1
        points = HAND_SCORES[rank]
        total += points
        total_squared += points * points

    mean = total / count
    if exact or count < 2:
        stderr = 0.0
    else:
        variance = max(0.0, total_squared / count - mean * mean)
        stderr = math.sqrt(variance / count)

    return Outcome(
        positions=positions,
        expected_points=mean,
        distribution={rank: n / count for rank, n in tally.items()},
        draws=count,
        exact=exact,
        standard_error=stderr,
    )


def all_discards(hand_size: int, max_discards: int = MAX_DISCARDS) -> list[frozenset[int]]:
    """Every legal discard, smallest first."""
    return [
        frozenset(combo)
        for size in range(min(max_discards, hand_size) + 1)
        for combo in combinations(range(hand_size), size)
    ]


def best_discards(
    hand: Sequence[Card],
    *,
    trials: int = DEFAULT_TRIALS,
    top: int = 5,
    rng: random.Random | None = None,
) -> list[Outcome]:
    """Every legal discard, ranked by expected points, best first.

    Ties are broken towards discarding fewer cards: with nothing to choose
    between two options, keeping more of a known hand is the smaller bet.
    """
    rng = rng or random.Random(0)
    outcomes = [
        evaluate_discard(hand, positions, trials=trials, rng=rng)
        for positions in all_discards(len(hand))
    ]
    outcomes.sort(key=lambda o: (-o.expected_points, o.discarded, sorted(o.positions)))
    return outcomes[:top]


def statistical_ties(outcomes: Sequence[Outcome]) -> list[Outcome]:
    """Options indistinguishable from the leader.

    Sampling error is real and the honest answer is often "these three are the
    same". Two exactly-computed options tie only if their means are equal;
    sampled ones tie when they overlap within `TIE_SIGMAS` standard errors of
    the combined estimate.
    """
    if not outcomes:
        return []
    leader = outcomes[0]
    tied = [leader]
    for other in outcomes[1:]:
        margin = TIE_SIGMAS * math.sqrt(
            leader.standard_error**2 + other.standard_error**2
        )
        if leader.expected_points - other.expected_points <= margin:
            tied.append(other)
    return tied


def advise(
    hand: Sequence[Card],
    *,
    trials: int = DEFAULT_TRIALS,
    top: int = 5,
    rng: random.Random | None = None,
) -> str:
    """A printable recommendation."""
    ranked = best_discards(hand, trials=trials, top=top, rng=rng)
    if not ranked:
        return "no legal discard"
    tied = statistical_ties(ranked)

    lines = [f"holding {' '.join(str(c) for c in hand)} -> {score_cards(list(hand)).value}"]
    lines += [f"  {i}. {o.describe(hand)}" for i, o in enumerate(ranked, start=1)]
    if len(tied) > 1:
        lines.append(
            f"  the top {len(tied)} are within sampling error of each other; "
            "any of them is a defensible choice"
        )
    return "\n".join(lines)
