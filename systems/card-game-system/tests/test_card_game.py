"""Tests for the deck, the scorer, and the round logic."""

from __future__ import annotations

import pytest

from card_game import Card, Deck, Game, Hand, HandRank, OutOfCards, Suit, score_cards
from card_game.display import parse_discards
from card_game.hand import HAND_SCORES, MAX_DISCARDS


def hand_of(*specs: str) -> list[Card]:
    """Build cards from compact specs like 'AS' (ace of spades), '10H'."""
    suits = {"C": Suit.CLUBS, "D": Suit.DIAMONDS, "H": Suit.HEARTS, "S": Suit.SPADES}
    return [Card(suits[s[-1]], s[:-1]) for s in specs]


# --------------------------------------------------------------------------- #
# Cards
# --------------------------------------------------------------------------- #


def test_suit_colours():
    assert Card(Suit.SPADES, "A").color == "black"
    assert Card(Suit.HEARTS, "A").color == "red"


def test_invalid_rank_is_rejected_at_construction():
    with pytest.raises(ValueError, match="valid rank"):
        Card(Suit.SPADES, "1")


def test_card_renders_with_its_suit_symbol():
    assert str(Card(Suit.HEARTS, "10")) == "10♥"


def test_cards_are_hashable_and_comparable():
    assert Card(Suit.SPADES, "A") == Card(Suit.SPADES, "A")
    assert len({Card(Suit.SPADES, "A"), Card(Suit.SPADES, "A")}) == 1


# --------------------------------------------------------------------------- #
# Deck
# --------------------------------------------------------------------------- #


def test_deck_has_52_unique_cards():
    deck = Deck(seed=1)
    assert len(deck) == 52
    assert len(set(deck.cards)) == 52


def test_dealing_removes_from_the_deck_and_records_the_card():
    deck = Deck(seed=1)
    card = deck.deal()
    assert len(deck) == 51
    assert deck.dealt == [card]


def test_empty_deck_raises_instead_of_returning_none():
    """The original returned None, which landed in the hand and crashed scoring."""
    deck = Deck(seed=1)
    deck.deal_many(52)
    with pytest.raises(OutOfCards):
        deck.deal()


def test_deal_many_refuses_a_partial_fill():
    deck = Deck(seed=1)
    deck.deal_many(50)
    with pytest.raises(OutOfCards, match="2 remain"):
        deck.deal_many(3)


def test_recycle_returns_discards_to_the_bottom():
    deck = Deck(seed=1)
    deck.deal_many(10)
    deck.recycle()
    assert len(deck) == 52
    assert deck.dealt == []


def test_same_seed_gives_the_same_deal():
    assert Deck(seed=7).deal_many(5) == Deck(seed=7).deal_many(5)


def test_different_seeds_generally_differ():
    assert Deck(seed=1).deal_many(5) != Deck(seed=2).deal_many(5)


# --------------------------------------------------------------------------- #
# Scoring -- including the two bugs the original had
# --------------------------------------------------------------------------- #


def test_six_card_flush_is_a_flush():
    """`5 in suit_counts.values()` was False for six of a suit, scoring nothing."""
    cards = hand_of("2H", "4H", "6H", "8H", "10H", "QH", "3S")
    assert score_cards(cards) is HandRank.FLUSH


def test_seven_card_flush_is_a_flush():
    cards = hand_of("2H", "4H", "6H", "8H", "10H", "QH", "KH")
    assert score_cards(cards) is HandRank.FLUSH


def test_exactly_five_of_a_suit_is_still_a_flush():
    cards = hand_of("2H", "4H", "6H", "8H", "10H", "3S", "5C")
    assert score_cards(cards) is HandRank.FLUSH


def test_two_triples_are_a_full_house():
    """3+3 is a full house; the original required an exact pair and scored 3Kind."""
    cards = hand_of("2H", "2S", "2C", "5H", "5S", "5C", "9D")
    assert score_cards(cards) is HandRank.FULL_HOUSE


def test_classic_full_house():
    cards = hand_of("2H", "2S", "2C", "5H", "5S", "9C", "KD")
    assert score_cards(cards) is HandRank.FULL_HOUSE


def test_four_of_a_kind_outranks_everything_below_it():
    cards = hand_of("2H", "2S", "2C", "2D", "5H", "5S", "5C")
    assert score_cards(cards) is HandRank.FOUR_KIND


def test_four_of_a_kind_beats_a_flush_in_the_same_hand():
    cards = hand_of("2H", "2S", "2C", "2D", "5H", "8H", "9H")
    assert score_cards(cards) is HandRank.FOUR_KIND


def test_full_house_beats_a_flush():
    cards = hand_of("2H", "2S", "2C", "5H", "5D", "8H", "9H")
    assert score_cards(cards) is HandRank.FULL_HOUSE


def test_three_of_a_kind_without_a_second_pair():
    cards = hand_of("2H", "2S", "2C", "5H", "8D", "9C", "KS")
    assert score_cards(cards) is HandRank.THREE_KIND


def test_two_pair():
    cards = hand_of("2H", "2S", "5C", "5H", "8D", "9C", "KS")
    assert score_cards(cards) is HandRank.TWO_PAIR


def test_three_pairs_still_score_two_pair():
    cards = hand_of("2H", "2S", "5C", "5H", "8D", "8C", "KS")
    assert score_cards(cards) is HandRank.TWO_PAIR


def test_single_pair():
    cards = hand_of("2H", "2S", "5C", "7H", "8D", "9C", "KS")
    assert score_cards(cards) is HandRank.PAIR


def test_nothing():
    cards = hand_of("2H", "4S", "6C", "8H", "10D", "QC", "KS")
    assert score_cards(cards) is HandRank.NOTHING


def test_empty_hand_scores_nothing():
    assert score_cards([]) is HandRank.NOTHING


def test_every_rank_has_a_score():
    assert set(HAND_SCORES) == set(HandRank)


def test_score_ordering_matches_rank_ordering():
    ordered = [
        HandRank.FOUR_KIND, HandRank.FULL_HOUSE, HandRank.FLUSH,
        HandRank.THREE_KIND, HandRank.TWO_PAIR, HandRank.PAIR, HandRank.NOTHING,
    ]
    points = [HAND_SCORES[r] for r in ordered]
    assert points == sorted(points, reverse=True)


# --------------------------------------------------------------------------- #
# Hand
# --------------------------------------------------------------------------- #


def test_discard_removes_the_right_positions():
    hand = Hand(hand_of("2H", "3S", "4C", "5H", "6D", "7C", "8S"))
    removed = hand.discard({0, 2})
    assert [str(c) for c in removed] == ["2♥", "4♣"]
    assert len(hand) == 5


def test_discard_beyond_the_limit_is_rejected():
    hand = Hand(hand_of("2H", "3S", "4C", "5H", "6D", "7C", "8S"))
    with pytest.raises(ValueError, match=str(MAX_DISCARDS)):
        hand.discard({0, 1, 2, 3, 4, 5})


def test_discarding_a_position_that_does_not_exist_is_an_error():
    """Silently ignoring it would look like a discard the player never asked for."""
    hand = Hand(hand_of("2H", "3S"))
    with pytest.raises(IndexError, match=r"\[9\]"):
        hand.discard({9})


def test_reset_clears_the_hand():
    hand = Hand(hand_of("2H", "3S"))
    hand.reset()
    assert len(hand) == 0


def test_points_follow_the_score():
    hand = Hand(hand_of("2H", "2S", "5C", "7H", "8D", "9C", "KS"))
    assert hand.points == HAND_SCORES[HandRank.PAIR]


# --------------------------------------------------------------------------- #
# Discard parsing
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("text", ["123", "1 2 3", "1,2,3", "1;2;3", " 1  2 3 "])
def test_discard_formats_all_parse_the_same(text):
    assert parse_discards(text) == {0, 1, 2}


def test_parse_is_one_based_to_zero_based():
    assert parse_discards("1") == {0}
    assert parse_discards("7") == {6}


def test_out_of_range_digits_are_ignored():
    # 0 and 8/9 are outside a seven-card hand; only the valid digits survive.
    assert parse_discards("089") == set()
    assert parse_discards("0891") == {0}


def test_empty_response_discards_nothing():
    assert parse_discards("") == set()


def test_repeated_digits_collapse():
    assert parse_discards("111") == {0}


# --------------------------------------------------------------------------- #
# Game loop
# --------------------------------------------------------------------------- #


def test_round_deals_seven_cards():
    game = Game(deck=Deck(seed=3))
    game.deal_round()
    assert len(game.hand) == 7


def test_discards_are_replaced_so_the_hand_stays_full():
    game = Game(deck=Deck(seed=3))
    game.deal_round()
    game.apply_discards({0, 1})
    assert len(game.hand) == 7


def test_no_discards_leaves_the_hand_untouched():
    game = Game(deck=Deck(seed=3))
    game.deal_round()
    before = list(game.hand.cards)
    game.apply_discards(set())
    assert game.hand.cards == before


def test_a_scoring_hand_is_recorded_and_play_continues():
    game = Game(deck=Deck(seed=3))
    game.hand.cards = hand_of("2H", "2S", "5C", "7H", "8D", "9C", "KS")
    assert game.finish_round() is HandRank.PAIR
    assert game.round_scores == [HandRank.PAIR]
    assert game.over is False


def test_a_non_scoring_hand_ends_the_game():
    game = Game(deck=Deck(seed=3))
    game.hand.cards = hand_of("2H", "4S", "6C", "8H", "10D", "QC", "KS")
    assert game.finish_round() is HandRank.NOTHING
    assert game.round_scores == []
    assert game.over is True


def test_total_score_accumulates_across_rounds():
    game = Game(deck=Deck(seed=3))
    game.round_scores = [HandRank.PAIR, HandRank.FLUSH]
    assert game.total_score == HAND_SCORES[HandRank.PAIR] + HAND_SCORES[HandRank.FLUSH]


def test_deck_is_recycled_rather_than_exhausted_over_many_rounds():
    """Seven rounds of seven cards exceeds 52; the game must not run dry."""
    game = Game(deck=Deck(seed=3))
    for _ in range(12):
        game.deal_round()
        assert len(game.hand) == 7
        game.apply_discards({0, 1, 2})
        assert len(game.hand) == 7
