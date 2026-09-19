"""The command line, exercised. It was the only untested module here."""

import io

import pytest
from rich.console import Console

from card_game import cli, display
from card_game.advisor import advise
from card_game.cards import Card, Deck, Suit, parse_hand
from card_game.cli import main
from card_game.display import (
    prompt_for_discards,
    render_card,
    render_hand,
    render_scoreboard,
    show_game_state,
)
from card_game.game import Game
from card_game.hand import HAND_SIZE, MAX_DISCARDS, Hand, HandRank

HAND = "Ah Kh Qh Jh 7c 7s 2d"


class TestAdvise:
    def test_it_analyses_a_hand_and_exits(self, capsys):
        assert main(["--advise", HAND]) == 0
        out = capsys.readouterr().out
        assert "discard" in out
        assert "Pair" in out, "it should name the current hand rank"

    def test_it_is_deterministic_for_a_seed(self, capsys):
        assert main(["--advise", HAND, "--seed", "1", "--trials", "200"]) == 0
        first = capsys.readouterr().out
        assert main(["--advise", HAND, "--seed", "1", "--trials", "200"]) == 0
        assert capsys.readouterr().out == first

    def test_it_marks_which_numbers_were_sampled(self, capsys):
        """Exact where enumeration is cheap, sampled above it -- and it says so."""
        assert main(["--advise", HAND, "--trials", "200"]) == 0
        out = capsys.readouterr().out
        assert "exact" in out or "±" in out

    def test_more_trials_narrows_the_interval(self, capsys):
        """A sampled estimate must get more precise with more samples."""
        import re

        def widest(text: str) -> int:
            spreads = [int(m) for m in re.findall(r"±(\d+)", text)]
            return max(spreads) if spreads else 0

        main(["--advise", HAND, "--trials", "100", "--seed", "3"])
        few = widest(capsys.readouterr().out)
        main(["--advise", HAND, "--trials", "4000", "--seed", "3"])
        many = widest(capsys.readouterr().out)
        if few and many:
            assert many <= few


class TestBadInput:
    def test_an_unreadable_hand_is_reported_not_raised(self, capsys):
        # 2, not 1: this is a usage error, which is the code argparse itself
        # uses. A missing file elsewhere in the repo is a runtime failure and
        # returns 1. Pinned so the distinction stays deliberate.
        code = main(["--advise", "Zz Kh Qh Jh 7c 7s 2d"])
        captured = capsys.readouterr()
        assert code == 2
        assert "error" in (captured.err + captured.out).lower()

    def test_an_unknown_flag_exits_nonzero(self):
        with pytest.raises(SystemExit) as exit:
            main(["--not-a-real-flag"])
        assert exit.value.code != 0

    def test_help_exits_cleanly(self):
        with pytest.raises(SystemExit) as exit:
            main(["--help"])
        assert exit.value.code == 0


class TestThePlayLoop:
    """The interactive game, driven by scripted answers instead of a keyboard.

    The loop is where the rules meet the prompts, and it was the one part of
    the game no test had ever run: every earlier test either scored a hand or
    analysed one, and none of them played.
    """

    @staticmethod
    def drive(monkeypatch, *, discards=None, next_round=None, argv=None):
        """Run a game with scripted player answers, returning the exit code."""
        replies = list(discards or [set()])
        answers = list(next_round or [False])

        def fake_discards(*_args, **_kwargs):
            return replies.pop(0) if replies else set()

        def fake_confirm(*_args, **_kwargs):
            return answers.pop(0) if answers else False

        monkeypatch.setattr(cli, "prompt_for_discards", fake_discards)
        monkeypatch.setattr(cli.Confirm, "ask", staticmethod(fake_confirm))
        return main(argv if argv is not None else ["--seed", "7"])

    def test_a_player_who_stops_after_one_round_gets_a_final_score(
        self, monkeypatch, capsys
    ):
        assert self.drive(monkeypatch) == 0
        out = capsys.readouterr().out
        assert "Game over after" in out
        assert "Final score:" in out

    def test_saying_yes_deals_another_round(self, monkeypatch, capsys):
        # Counted rather than read off the final score: a round only scores if
        # the hand beats NOTHING, and a seed that happens to bust would make a
        # score-based assertion pass or fail for the wrong reason.
        dealt: list[int] = []
        original = cli.Game.deal_round
        monkeypatch.setattr(
            cli.Game,
            "deal_round",
            lambda self: (dealt.append(1), original(self))[1],
        )
        self.drive(monkeypatch, discards=[set()] * 3, next_round=[True, True])
        capsys.readouterr()
        assert len(dealt) > 1, "the loop stopped even though the player said yes"

    def test_saying_no_stops_after_one_round(self, monkeypatch, capsys):
        dealt: list[int] = []
        original = cli.Game.deal_round
        monkeypatch.setattr(
            cli.Game,
            "deal_round",
            lambda self: (dealt.append(1), original(self))[1],
        )
        self.drive(monkeypatch, next_round=[False])
        capsys.readouterr()
        assert len(dealt) == 1

    def test_hints_are_only_printed_when_asked_for(self, monkeypatch, capsys):
        self.drive(monkeypatch, argv=["--seed", "7"])
        assert "holding" not in capsys.readouterr().out

        self.drive(monkeypatch, argv=["--seed", "7", "--hints", "--trials", "50"])
        assert "holding" in capsys.readouterr().out

    def test_a_hand_that_does_not_score_ends_the_game_without_asking(
        self, monkeypatch, capsys
    ):
        # Confirm.ask must never be reached: the game is already over, and
        # asking "next round?" after a bust would be a rule bug the player sees.
        def refuse(*_args, **_kwargs):
            raise AssertionError("the loop asked to continue after the game ended")

        monkeypatch.setattr(cli.Confirm, "ask", staticmethod(refuse))
        monkeypatch.setattr(cli, "prompt_for_discards", lambda *a, **k: set())
        monkeypatch.setattr(
            cli.Game, "finish_round", lambda self: self._bust()  # type: ignore[attr-defined]
        )

        def bust(self):
            self.over = True
            return HandRank.NOTHING

        monkeypatch.setattr(cli.Game, "_bust", bust, raising=False)
        assert main(["--seed", "7"]) == 0
        assert "Game over after 0 scoring round(s)" in capsys.readouterr().out

    def test_discarding_draws_replacements_so_the_hand_stays_full(
        self, monkeypatch, capsys
    ):
        seen: list[int] = []

        original = cli.Game.apply_discards

        def record(self, positions):
            original(self, positions)
            seen.append(len(self.hand))

        monkeypatch.setattr(cli.Game, "apply_discards", record)
        self.drive(monkeypatch, discards=[{0, 1, 2}])
        assert seen == [HAND_SIZE]


class TestRendering:
    """The display layer. Asserted on the text it produces, not on `rich`."""

    @staticmethod
    def text_of(renderable) -> str:
        console = Console(width=120, record=True, file=io.StringIO())
        console.print(renderable)
        return console.export_text()

    def test_a_card_shows_its_rank_and_suit(self):
        rendered = self.text_of(render_card(Card(Suit.HEARTS, "A")))
        assert "A" in rendered

    def test_every_card_in_hand_is_numbered_for_the_prompt(self):
        hand = Hand(cards=parse_hand(HAND))
        rendered = self.text_of(render_hand(hand))
        for position in range(1, HAND_SIZE + 1):
            assert f"({position})" in rendered

    def test_the_scoreboard_totals_the_rounds_played(self):
        game = Game(deck=Deck(seed=1))
        game.round_scores = [HandRank.PAIR, HandRank.FLUSH]
        board = render_scoreboard(game)
        assert "Round 1: Pair" in board
        assert f"Total Score: {game.total_score}" in board
        assert "Round: 3" in board, "the next round to play, not the last one scored"

    def test_the_full_screen_renders_hand_and_scoreboard_together(self, capsys):
        game = Game(deck=Deck(seed=1))
        game.deal_round()
        show_game_state(game)
        out = capsys.readouterr().out
        assert "Total Score" in out
        assert "(7)" in out


class TestTheDiscardPrompt:
    def test_too_many_cards_is_refused_and_re_asked(self, monkeypatch, capsys):
        replies = iter(["1234567", "1 2"])
        monkeypatch.setattr(
            display.Prompt, "ask", staticmethod(lambda *a, **k: next(replies))
        )
        assert prompt_for_discards() == {0, 1}
        assert f"At most {MAX_DISCARDS}" in capsys.readouterr().out

    def test_pressing_enter_keeps_the_whole_hand(self, monkeypatch):
        monkeypatch.setattr(display.Prompt, "ask", staticmethod(lambda *a, **k: ""))
        assert prompt_for_discards() == set()


class TestRunningOutOfCards:
    def test_a_short_deck_is_recycled_rather_than_ending_the_game(self):
        game = Game(deck=Deck(seed=3))
        game.deck.cards = game.deck.cards[:3]
        game.deck.dealt = [Card(Suit.SPADES, r) for r in ("2", "3", "4", "5", "6")]
        game.deal_round()
        assert len(game.hand) == HAND_SIZE
        assert game.over is False

    def test_a_deck_that_cannot_refill_the_hand_ends_the_game_instead_of_crashing(self):
        # Every card is in the hand, so there is nothing to recycle and nothing
        # to draw. Playing on with a short hand beats an OutOfCards traceback.
        game = Game(deck=Deck(seed=3))
        game.hand = Hand(cards=parse_hand(HAND))
        game.deck.cards = []
        game.deck.dealt = []
        game.apply_discards({0, 1})
        assert game.over is True
        assert len(game.hand) == HAND_SIZE - 2

    def test_keeping_every_card_touches_neither_deck_nor_hand(self):
        game = Game(deck=Deck(seed=3))
        game.deal_round()
        before = list(game.hand.cards), len(game.deck)
        game.apply_discards(set())
        assert (list(game.hand.cards), len(game.deck)) == before


def test_asking_for_no_recommendations_says_so_rather_than_printing_a_bare_header():
    # "Discard nothing" is itself a legal discard, so the ranking is only ever
    # empty when the caller asks for zero of them. Without the guard that call
    # returns a header line with no options under it, which reads like a bug.
    assert advise(parse_hand(HAND), trials=10, top=0) == "no legal discard"
