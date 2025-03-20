import random
# To import Card, use absolute imports
from card import Card

class Deck:
    """
    A standard deck that holds a collection of cards and is able to shuffle & deal the cards

    Attributes:
        cards (list): Holds undealt cards in the deck
        dealt_cards (list): Tracks already dealt cards
    """
    def __init__(self):
        """
        Initialize the deck with all 52 cards while tracks the already dealt cards 
        Shuffle the full deck initially 
        Take no arguments 
        """
        self.cards = [] # holds undealt cards
        self.dealt_cards = [] # tracks already dealt cards
        self._initialize_deck()
        self.shuffle(full_deck=True)  # Shuffle the full deck on initialization

    def _initialize_deck(self):
        """
        Creates all 52 cards  (13 ranks x 4 suits) and adds them to the deck.
        """
        ranks = ['2', '3', '4', '5', '6', '7', '8', '9', '10', 'J', 'Q', 'K', 'A']
        suits = [Card.CLUBS, Card.DIAMONDS, Card.HEARTS, Card.SPADES]

        for suit in suits:
            for rank in ranks:
                self.cards.append(Card(suit, rank))

    def __len__(self):
        """
        Returns the number of cards left in the deck
        """
        return len(self.cards)

    def deal(self):
        """
        Removes the top card from the deck and returns it
        """
        if len(self.cards) != 0:
            card = self.cards.pop(0)
            self.dealt_cards.append(card)
            return card
        print("No cards left")
        return None

    def shuffle(self, full_deck = False):
        """
        Shuffles the already dealt cards and places them at the bottom of the deck
        It should not shuffle the undealt cards
        """
        if full_deck:
            random.shuffle(self.cards)  # Initial shuffle of all cards
        else:
            random.shuffle(self.dealt_cards)  # Shuffle the dealt cards
            self.cards += self.dealt_cards  # Add shuffled dealt cards to bottom
            self.dealt_cards = []  # Clear dealt cards after reshuffling
