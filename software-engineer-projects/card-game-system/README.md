# Card Game

A single-player poker-style draw game. You're dealt seven cards, discard up to
five, and the resulting hand is scored. Score nothing and the game ends.

```
┌─────┐┌─────┐┌─────┐┌─────┐┌─────┐┌─────┐┌─────┐   Round 1: Pair 10
│ 2♥  ││ 2♠  ││ 5♣  ││ 7♥  ││ 8♦  ││ 9♣  ││ K♠  │   Round 2: Flush 200
└─────┘└─────┘└─────┘└─────┘└─────┘└─────┘└─────┘   ------
  (1)    (2)    (3)    (4)    (5)    (6)    (7)     Total Score: 210
                                                     Round: 3
                                                     Cards Left: 31
```

| Hand | Points |
|---|---:|
| Four of a kind | 2000 |
| Full house | 250 |
| Flush | 200 |
| Three of a kind | 100 |
| Two pair | 50 |
| Pair | 10 |

## Run it

```bash
python3 -m venv .venv && .venv/bin/pip install -e ".[dev]"
card-game --seed 42      # --seed makes the shuffle reproducible
pytest -q                # 48 tests
ruff check .
```

## Layout

```
src/card_game/
  cards.py     Card, Suit, Deck          (no I/O)
  hand.py      Hand and the scorer       (pure)
  game.py      round and game state      (no I/O)
  display.py   rich rendering, prompts   (the only module that prints)
  cli.py       entry point
```

The rules don't print and the display doesn't decide anything. That split is
what lets a test play twelve full rounds without a terminal.

## Two scoring bugs this version fixes

Both came from testing for an *exact* count in a seven-card hand, where
five-card poker intuitions quietly stop holding.

**A six- or seven-card flush scored as nothing.**

```python
if 5 in suit_count.values():   # False when you hold six hearts
```

With six cards of a suit the value is `6`, so `5 in values()` is `False` — the
best flushes in the game failed to score. Now `max(...) >= 5`.

**Two triples scored as three of a kind, not a full house.**

```python
if 3 in rank_count.values() and 2 in rank_count.values():
```

Holding 2♥2♠2♣ 5♥5♠5♣ is a full house — three of one rank plus a pair from the
other — but there is no rank with exactly two cards, so the check failed and it
scored 100 instead of 250. Now it asks whether a second group has *at least*
two.

Also fixed:

- `Deck.deal()` returned `None` and printed "No cards left" when empty. The
  `None` went into the player's hand and crashed later in scoring, far from the
  cause. It now raises `OutOfCards`, and the game recycles discards instead of
  running dry — the rules end the game on a non-scoring hand, not on an empty
  deck.
- The "up to 5 cards" limit was stated in the prompt and enforced nowhere.
- Discarding an out-of-range position was silently ignored, so a mis-parsed
  reply looked like a discard the player never asked for.
- `Hand.discard()` existed but the game loop bypassed it and mutated
  `hand.cards` directly.
- Modules used top-level absolute imports (`from card import Card`), so the
  code only ran from inside its own directory.

## Notes

- Scoring uses all seven cards, not the best five, so a flush needs five of a
  suit anywhere in the hand.
- Straights are not scored — they aren't in the table above.
- The deck reshuffles discards when it runs low, so a long game keeps dealing.
