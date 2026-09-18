"""The discard advisor: exact where affordable, sampled where not, honest about which."""

from __future__ import annotations

import math
import random
from itertools import combinations

import pytest

from card_game import (
    Card,
    HandRank,
    Suit,
    advise,
    all_discards,
    best_discards,
    evaluate_discard,
    parse_hand,
    statistical_ties,
    unseen_cards,
)
from card_game.advisor import EXACT_LIMIT, full_deck
from card_game.hand import HAND_SCORES, MAX_DISCARDS


def hand(text: str) -> list[Card]:
    return parse_hand(text)


FLUSH_DRAW = "Ah Kh 9h 4h 7c 7s 2d"
TRIPS = "Qh Qc Qs 8d 5c 3h 2s"
ROYAL_DRAW = "Ah Kh Qh Jh 7c 7s 2d"


# --------------------------------------------------------------------------- #
# The unseen deck
# --------------------------------------------------------------------------- #


def test_the_unseen_deck_excludes_the_players_own_cards():
    """Otherwise the odds of improving a pair are quietly overstated."""
    cards = hand(FLUSH_DRAW)
    pool = unseen_cards(cards)
    assert len(pool) == 52 - len(cards)
    assert not set(pool) & set(cards)


def test_the_full_deck_is_a_deck():
    deck = full_deck()
    assert len(deck) == 52
    assert len(set(deck)) == 52
    assert {c.suit for c in deck} == set(Suit)


# --------------------------------------------------------------------------- #
# Enumerating the choices
# --------------------------------------------------------------------------- #


def test_every_legal_discard_is_enumerated():
    options = all_discards(7)
    # C(7,0) + ... + C(7,5) = 1+7+21+35+35+21
    assert len(options) == 120
    assert frozenset() in options
    assert max(len(o) for o in options) == MAX_DISCARDS


def test_discarding_more_than_the_limit_is_rejected():
    with pytest.raises(ValueError, match="at most"):
        evaluate_discard(hand(TRIPS), {0, 1, 2, 3, 4, 5})


def test_an_out_of_range_position_is_rejected():
    with pytest.raises(IndexError, match="no card at position"):
        evaluate_discard(hand(TRIPS), {9})


# --------------------------------------------------------------------------- #
# Exact vs sampled
# --------------------------------------------------------------------------- #


def test_keeping_everything_is_exact_and_needs_no_draws():
    outcome = evaluate_discard(hand(TRIPS), set())
    assert outcome.exact
    assert outcome.draws == 1
    assert outcome.standard_error == 0.0
    assert outcome.expected_points == HAND_SCORES[HandRank.THREE_KIND]


def test_a_one_card_discard_is_computed_exactly():
    """45 unseen cards is cheaper to enumerate than to sample."""
    outcome = evaluate_discard(hand(TRIPS), {6})
    assert outcome.exact
    assert outcome.draws == 45
    assert outcome.standard_error == 0.0


def test_a_two_card_discard_is_computed_exactly():
    outcome = evaluate_discard(hand(TRIPS), {5, 6})
    assert outcome.exact
    assert outcome.draws == math.comb(45, 2) == 990
    assert outcome.draws <= EXACT_LIMIT


def test_a_large_discard_is_sampled_and_says_so():
    outcome = evaluate_discard(hand(TRIPS), {2, 3, 4, 5, 6}, trials=200)
    assert not outcome.exact
    assert outcome.draws == 200
    assert outcome.standard_error > 0


def test_an_exact_answer_is_reproducible_without_a_seed():
    a = evaluate_discard(hand(TRIPS), {6})
    b = evaluate_discard(hand(TRIPS), {6}, rng=random.Random(99))
    assert a.expected_points == b.expected_points


def test_a_sampled_answer_is_reproducible_with_a_seed():
    kwargs = {"trials": 100}
    a = evaluate_discard(hand(TRIPS), {2, 3, 4, 5}, rng=random.Random(7), **kwargs)
    b = evaluate_discard(hand(TRIPS), {2, 3, 4, 5}, rng=random.Random(7), **kwargs)
    assert a.expected_points == b.expected_points


def test_the_exact_answer_matches_a_hand_rolled_enumeration():
    """The estimator has no thumb on the scale."""
    cards = hand(TRIPS)
    pool = unseen_cards(cards)
    kept = cards[:6]
    from card_game import score_cards

    expected = sum(
        HAND_SCORES[score_cards([*kept, card])] for card in pool
    ) / len(pool)
    assert evaluate_discard(cards, {6}).expected_points == pytest.approx(expected)


def test_sampling_converges_on_the_exact_answer():
    """Three discards is exact-able by brute force here, if slowly."""
    cards = hand(TRIPS)
    positions = {4, 5, 6}
    pool = unseen_cards(cards)
    kept = [c for i, c in enumerate(cards) if i not in positions]
    from card_game import score_cards

    truth = sum(
        HAND_SCORES[score_cards([*kept, *draw])]
        for draw in combinations(pool, 3)
    ) / math.comb(len(pool), 3)

    sampled = evaluate_discard(cards, positions, trials=4000, rng=random.Random(3))
    assert not sampled.exact
    # Within four standard errors of the truth.
    assert abs(sampled.expected_points - truth) < 4 * sampled.standard_error


# --------------------------------------------------------------------------- #
# The distribution
# --------------------------------------------------------------------------- #


def test_the_distribution_is_a_distribution():
    outcome = evaluate_discard(hand(FLUSH_DRAW), {4, 5, 6}, trials=300)
    assert sum(outcome.distribution.values()) == pytest.approx(1.0)
    assert all(0.0 <= p <= 1.0 for p in outcome.distribution.values())


def test_the_expected_points_match_the_distribution():
    outcome = evaluate_discard(hand(FLUSH_DRAW), {4, 5}, trials=300)
    implied = sum(
        HAND_SCORES[rank] * p for rank, p in outcome.distribution.items()
    )
    assert outcome.expected_points == pytest.approx(implied)


def test_scoring_probability_is_the_complement_of_nothing():
    outcome = evaluate_discard(hand("2c 5d 8h Js Kc 3h 7s"), {0, 1, 2, 3, 4}, trials=300)
    nothing = outcome.distribution.get(HandRank.NOTHING, 0.0)
    assert outcome.probability_of_scoring == pytest.approx(1 - nothing)


def test_a_made_hand_that_is_kept_cannot_get_worse():
    """Keeping trips scores trips or better, with certainty."""
    outcome = evaluate_discard(hand(TRIPS), {5, 6})
    assert outcome.probability_of_scoring == 1.0
    assert HandRank.NOTHING not in outcome.distribution


# --------------------------------------------------------------------------- #
# The advice itself
# --------------------------------------------------------------------------- #


def test_it_keeps_four_to_a_flush():
    best = best_discards(hand(FLUSH_DRAW), trials=600, rng=random.Random(1))[0]
    # Positions 0-3 are the hearts; the right move is to throw the other three.
    assert best.positions == frozenset({4, 5, 6})


def test_it_keeps_an_open_ended_straight_draw():
    cards = hand("8h 9c 10s Jd 3c 5h 2s")
    best = best_discards(cards, trials=600, rng=random.Random(1))[0]
    assert best.positions == frozenset({4, 5, 6})


def test_it_chases_a_royal_flush_over_keeping_a_pair():
    """Four to the royal is worth more than two sevens, by a lot."""
    ranked = best_discards(hand(ROYAL_DRAW), trials=600, rng=random.Random(1))
    assert ranked[0].positions == frozenset({4, 5, 6})
    keep_pair = evaluate_discard(hand(ROYAL_DRAW), {0, 1, 2, 3}, trials=600,
                                 rng=random.Random(1))
    assert ranked[0].expected_points > keep_pair.expected_points


def test_it_draws_to_improve_trips():
    """Holding three queens, the four spare cards are worth replacing."""
    best = best_discards(hand(TRIPS), trials=600, rng=random.Random(1))[0]
    assert best.positions == frozenset({3, 4, 5, 6})


def test_results_come_back_best_first():
    ranked = best_discards(hand(FLUSH_DRAW), trials=300, rng=random.Random(1), top=10)
    points = [o.expected_points for o in ranked]
    assert points == sorted(points, reverse=True)


def test_ties_break_towards_discarding_fewer_cards():
    """With nothing to choose between two options, the smaller bet wins."""
    a = frozenset({0})
    b = frozenset({0, 1})
    ranked = best_discards(hand(TRIPS), trials=300, rng=random.Random(1), top=120)
    order = [o.positions for o in ranked]
    equal = [
        o for o in ranked
        if o.positions in (a, b)
    ]
    if len(equal) == 2 and equal[0].expected_points == equal[1].expected_points:
        assert order.index(a) < order.index(b)


def test_top_limits_the_results():
    assert len(best_discards(hand(TRIPS), trials=100, top=3)) == 3


# --------------------------------------------------------------------------- #
# Honesty about sampling error
# --------------------------------------------------------------------------- #


def test_exact_options_tie_only_when_they_are_equal():
    exact_a = evaluate_discard(hand(TRIPS), {6})
    exact_b = evaluate_discard(hand(TRIPS), {5})
    tied = statistical_ties([exact_a, exact_b])
    assert (len(tied) == 2) == (exact_a.expected_points == exact_b.expected_points)


def test_a_clear_winner_is_reported_as_one():
    keep_flush = evaluate_discard(hand(FLUSH_DRAW), {4, 5, 6}, trials=2000,
                                  rng=random.Random(5))
    throw_hearts = evaluate_discard(hand(FLUSH_DRAW), {0, 1, 2}, trials=2000,
                                    rng=random.Random(5))
    assert len(statistical_ties([keep_flush, throw_hearts])) == 1


def test_ties_are_symmetric_in_the_error_bars():
    """The margin uses both options' error, not just the leader's."""
    noisy = evaluate_discard(hand(TRIPS), {2, 3, 4, 5, 6}, trials=50,
                             rng=random.Random(11))
    leader = evaluate_discard(hand(TRIPS), {3, 4, 5, 6}, trials=50,
                              rng=random.Random(11))
    ordered = sorted([noisy, leader], key=lambda o: -o.expected_points)
    margin = 2.0 * math.sqrt(
        ordered[0].standard_error**2 + ordered[1].standard_error**2
    )
    gap = ordered[0].expected_points - ordered[1].expected_points
    assert (len(statistical_ties(ordered)) == 2) == (gap <= margin)


def test_statistical_ties_of_nothing_is_nothing():
    assert statistical_ties([]) == []


# --------------------------------------------------------------------------- #
# Rendering
# --------------------------------------------------------------------------- #


def test_the_advice_names_the_cards_and_the_current_rank():
    text = advise(hand(FLUSH_DRAW), trials=200, rng=random.Random(1))
    assert "Pair" in text
    assert "7♣" in text and "pts" in text


def test_keeping_everything_renders_as_nothing_discarded():
    outcome = evaluate_discard(hand(TRIPS), set())
    assert "discard nothing" in outcome.describe(hand(TRIPS))


def test_an_exact_option_is_labelled_exact_not_given_an_error_bar():
    outcome = evaluate_discard(hand(TRIPS), {6})
    assert "(exact)" in outcome.describe(hand(TRIPS))
    sampled = evaluate_discard(hand(TRIPS), {2, 3, 4, 5, 6}, trials=100)
    assert "±" in sampled.describe(hand(TRIPS))


def test_advising_an_empty_hand_says_so():
    assert advise([], trials=10) != ""
