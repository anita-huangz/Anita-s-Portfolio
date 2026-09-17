"""Straights and straight flushes: the ranks a seven-card game cannot omit."""

from __future__ import annotations

import pytest

from card_game import (
    Card,
    HandRank,
    Suit,
    parse_card,
    parse_hand,
    score_cards,
    straight_flush_high,
    straight_high,
)


def hand(text: str) -> list[Card]:
    return parse_hand(text)


# --------------------------------------------------------------------------- #
# Shorthand parsing
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("text", "rank", "suit"),
    [
        ("Ah", "A", Suit.HEARTS),
        ("as", "A", Suit.SPADES),
        ("10d", "10", Suit.DIAMONDS),
        ("Td", "10", Suit.DIAMONDS),
        ("2c", "2", Suit.CLUBS),
        ("  Qh  ", "Q", Suit.HEARTS),
    ],
)
def test_card_shorthand(text, rank, suit):
    card = parse_card(text)
    assert (card.rank, card.suit) == (rank, suit)


@pytest.mark.parametrize("bad", ["h", "", "Ax", "1h", "Zs", "110h"])
def test_bad_shorthand_raises(bad):
    with pytest.raises(ValueError):
        parse_card(bad)


def test_the_ten_does_not_need_a_special_case():
    """The rank is everything but the last character, so '10' just works."""
    assert parse_card("10h") == parse_card("Th")


def test_a_repeated_card_is_rejected():
    with pytest.raises(ValueError, match="appears twice"):
        parse_hand("Ah Kh Ah")


def test_a_hand_accepts_commas_or_spaces():
    assert parse_hand("Ah, Kh 9h") == parse_hand("Ah Kh 9h")


# --------------------------------------------------------------------------- #
# Straights
# --------------------------------------------------------------------------- #


def test_five_consecutive_ranks_make_a_straight():
    assert straight_high(hand("5c 6d 7h 8s 9c")) == "9"
    assert score_cards(hand("5c 6d 7h 8s 9c")) is HandRank.STRAIGHT


def test_four_consecutive_ranks_do_not():
    assert straight_high(hand("5c 6d 7h 8s Kc")) is None


def test_a_straight_inside_seven_cards_is_found():
    """Five of the seven make the run; the other two are irrelevant."""
    assert straight_high(hand("2c 5h 6d 7h 8s 9c Kd")) == "9"


def test_a_duplicate_rank_does_not_break_the_run():
    """Collapsing duplicates is the reason this is not a sort-and-scan.

    A pair inside the sequence leaves only six distinct ranks in seven cards,
    and a naive consecutive-pairs check over the sorted list sees the repeat
    as a gap.
    """
    assert straight_high(hand("5c 6d 6h 7h 8s 9c")) == "9"


def test_the_best_straight_is_reported_when_there_are_two():
    # 5-6-7-8-9 and 6-7-8-9-10 both present.
    assert straight_high(hand("5c 6d 7h 8s 9c 10d 2s")) == "10"


def test_the_wheel_is_a_straight():
    """A-2-3-4-5. The ace plays low, which is the case that gets lost."""
    assert straight_high(hand("Ac 2d 3h 4s 5c")) == "5"
    assert score_cards(hand("Ac 2d 3h 4s 5c")) is HandRank.STRAIGHT


def test_the_wheel_ranks_below_other_straights():
    """Its high card is the 5, not the ace it contains."""
    assert straight_high(hand("Ac 2d 3h 4s 5c")) == "5"
    assert straight_high(hand("Ac 2d 3h 4s 5c 6d")) == "6"


def test_a_broadway_straight_uses_the_ace_high():
    assert straight_high(hand("10c Jd Qh Ks Ac")) == "A"


def test_the_ace_does_not_wrap_around():
    """K-A-2-3-4 is not a straight, however the ace is valued."""
    assert straight_high(hand("Kc Ad 2h 3s 4c")) is None
    assert straight_high(hand("Qc Kd Ah 2s 3c")) is None


def test_an_empty_or_short_hand_has_no_straight():
    assert straight_high([]) is None
    assert straight_high(hand("Ah Kh")) is None


# --------------------------------------------------------------------------- #
# Straight flushes
# --------------------------------------------------------------------------- #


def test_five_suited_consecutive_cards_make_a_straight_flush():
    assert straight_flush_high(hand("5h 6h 7h 8h 9h")) == "9"
    assert score_cards(hand("5h 6h 7h 8h 9h")) is HandRank.STRAIGHT_FLUSH


def test_a_straight_and_a_flush_are_not_a_straight_flush():
    """The bug this checks for is `has_straight and has_flush`.

    These seven cards contain a 5-6-7-8-9 straight in mixed suits and five
    hearts that are not consecutive. Neither five-card selection is both.
    """
    cards = hand("5h 6d 7h 8s 9h Kh 2h")
    assert straight_high(cards) == "9"
    assert max(sum(1 for c in cards if c.suit is s) for s in Suit) >= 5
    assert straight_flush_high(cards) is None
    assert score_cards(cards) is HandRank.FLUSH


def test_a_suited_wheel_is_a_straight_flush():
    assert straight_flush_high(hand("Ah 2h 3h 4h 5h")) == "5"


def test_a_royal_flush_scores_as_a_straight_flush():
    assert straight_flush_high(hand("10s Js Qs Ks As")) == "A"
    assert score_cards(hand("10s Js Qs Ks As")) is HandRank.STRAIGHT_FLUSH


def test_the_higher_of_two_suited_runs_wins():
    # Hearts run 3-7, spades run 8-Q. Spades is higher.
    cards = hand("3h 4h 5h 6h 7h 8s 9s 10s Js Qs")
    assert straight_flush_high(cards) == "Q"


def test_a_straight_flush_outranks_four_of_a_kind():
    assert score_cards(hand("5h 6h 7h 8h 9h 5c 5d")) is HandRank.STRAIGHT_FLUSH


# --------------------------------------------------------------------------- #
# Ordering against the existing ranks
# --------------------------------------------------------------------------- #


def test_a_flush_still_outranks_a_straight():
    assert score_cards(hand("2h 5h 8h Jh Kh 3c 4d")) is HandRank.FLUSH
    assert score_cards(hand("5c 6d 7h 8s 9c Kd 2s")) is HandRank.STRAIGHT


def test_a_straight_outranks_three_of_a_kind():
    """Both are present here; the straight is the better five cards."""
    cards = hand("5c 6d 7h 8s 9c 9d 9h")
    assert score_cards(cards) is HandRank.STRAIGHT


def test_a_full_house_outranks_a_straight():
    cards = hand("5c 6d 7h 8s 9c 9d 5h")
    # 9-9 and 5-5 is only two pair, so this hand is the straight.
    assert score_cards(cards) is HandRank.STRAIGHT
    assert score_cards(hand("9c 9d 9h 5c 5d 2s 3h")) is HandRank.FULL_HOUSE
