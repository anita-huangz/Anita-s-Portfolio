from collections import defaultdict

FOUR_KIND = "4Kind"
FULL_HOUSE = "FullHouse"
FLUSH = "Flush"
THREE_KIND = "3Kind"
TWO_PAIR = "2Pair"
PAIR = "Pair"

HAND_SCORES = {
    FOUR_KIND: 2000,
    FULL_HOUSE: 250,
    FLUSH: 200,
    THREE_KIND: 100,
    TWO_PAIR: 50,
    PAIR: 10,
}


class Hand:
    """
    Represents a player's hand in a game 

    Methods:
        The method add(card) should take a Card and add it to the hand.
        The method reset() should clear the cards in the hand.
        The method discard(positions) takes a list of positions (0-6),
        and will remove the given positions from the hand.
    """
    def __init__(self):
        """
        The constructor should take no arguments.
        It must define a public attribute named cards that will represent collection of cards.
        This attribute should be a list of Card
        """
        self.cards = []

    def add(self, card):
        """
        Take a Card and add it to the hand
        """
        self.cards.append(card)

    def reset(self):
        """
        Clear the cards in the hand
        """
        self.cards = []

    def discard(self, positions):
        """
        Takes a list of positions (0-6),
        and will remove the given positions from the hand
        """
        self.cards = [card for i, card in enumerate(self.cards) if i not in positions]

    def score(self):
        """
        Return (as a string) the best key from HAND_SCORES that applies to the hand.
        """
        # Dictionaries to count occurrences of ranks and suits
        rank_count = defaultdict(int)
        suit_count = defaultdict(int)

        # Populate the rank_count and suit_count dictionaries
        for card in self.cards:
            rank_count[card.rank] += 1
            suit_count[card.suit] += 1

        # Check for Four of a Kind (4 cards of the same rank)
        if 4 in rank_count.values():
            return "4Kind"

        # Check for Full House (3 of a kind + 2 of a kind)
        if 3 in rank_count.values() and 2 in rank_count.values():
            return "FullHouse"

        # Check for Flush (5 or more cards of the same suit)
        if 5 in suit_count.values():
            return "Flush"

        # Check for Three of a Kind (3 cards of the same rank)
        if 3 in rank_count.values():
            return "3Kind"

        # Check for Two Pair (two different pairs of ranks)
        if 2 in rank_count.values():
            pair_count = 0
            for count in rank_count.values():
                # Increment pair count for each rank that appears exactly 2 times
                if count == 2:
                    pair_count += 1
            if pair_count >= 2:
                return "2Pair"

        # Check for Pair (2 cards of the same rank)
        if 2 in rank_count.values():
            return "Pair"

        # If nothing found
        return "None"
