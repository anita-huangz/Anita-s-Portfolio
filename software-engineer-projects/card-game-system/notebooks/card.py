class Card:
    # Class Attributes: Can be referenced as Card.CLUBS, Card.SUIT_SYMBOLS, etc.
    CLUBS = "clubs"
    DIAMONDS = "diamonds"
    HEARTS = "hearts"
    SPADES = "spades"
    SUIT_SYMBOLS = {
        CLUBS: "♣",
        SPADES: "♠",
        HEARTS: "♥",
        DIAMONDS: "♦",
    }

    def __init__(self, suit, rank):
        self.suit = suit
        self.rank = rank

    def color(self):
        """
        Returns "black" or "red" based on suit.
        """
        if self.suit in [self.CLUBS, self.SPADES]:
            return "black"
        else:
            return "red"

    def __repr__(self):
        return f"{self.rank}{self.SUIT_SYMBOLS[self.suit]}"
