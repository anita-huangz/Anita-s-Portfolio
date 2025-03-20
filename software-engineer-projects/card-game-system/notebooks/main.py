from rich.prompt import Confirm
from utils import show_game_state, prompt_for_discards
from deck import Deck
from hand import Hand


def main():
    """
    Implement this function according to the rules set out in README.md

    Use show_card_table and show_discard_prompt as needed.
    """
    # initialize game here
    game_over = False
    deck = Deck()  # Create a new shuffled deck
    round_scores = []  # Track scores for each round

    # this game loop will run until we hit the break below
    while True:
        # round initalization
        hand = Hand()

        # deal initial hand
        hand.cards = [deck.deal() for _ in range(7)]

        # Call show_game_state after hand is dealt!
        show_game_state(deck=deck, hand=hand, round_scores=round_scores)

        # process discards (see docstring for `prompt_for_discards` for details)
        discards = prompt_for_discards()
        for idx in discards:
            hand.cards[idx] = deck.deal()  # Replace discarded cards

        # show final hand with updated scores list
        # if hand did not score, set game_over to True
        show_game_state(deck=deck, hand=hand, round_scores=round_scores)

        current_score = hand.score()
        if current_score != "None":
            round_scores.append(current_score)
        else:
            game_over = True

        # DO NOT MODIFY BELOW THIS LINE -------------------

        # if game_over hasn't been set, will wait for confirmation of next round
        if game_over or not Confirm.ask("Next Round?"):
            break

    print("Did Not Score, Game Over!")


if __name__ == "__main__":
    main()
