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
| Straight flush | 5000 |
| Four of a kind | 2000 |
| Full house | 250 |
| Flush | 200 |
| Straight | 150 |
| Three of a kind | 100 |
| Two pair | 50 |
| Pair | 10 |

## Run it

```bash
python3 -m venv .venv && .venv/bin/pip install -e ".[dev]"
card-game --seed 42      # --seed makes the shuffle reproducible
card-game --hints        # show the best discards before each prompt
card-game --advise "Ah Kh Qh Jh 7c 7s 2d"   # analyse one hand and exit
pytest -q                # 114 tests
ruff check .
```

## It tells you what to throw away

The game asked for discards and gave the player nothing to decide with. The
choice is not obvious either — holding a pair and drawing five is a completely
different bet from holding four to a flush and drawing three, and which is
better depends on numbers nobody works out at the table.

`--advise` evaluates **every** legal discard (all 120 of them) and reports what
each is worth:

```
$ card-game --advise "Ah Kh Qh Jh 7c 7s 2d"
holding A♥ K♥ Q♥ J♥ 7♣ 7♠ 2♦ -> Pair
  1. discard 7♣, 7♠, 2♦                 534.6 pts (±136), scores 93.0%
  2. discard 7♣, 7♠                     309.6 pts (exact), scores 84.5%
  3. discard 7♣, 2♦                     308.9 pts (exact), scores 82.7%
  4. discard 7♠, 2♦                     308.9 pts (exact), scores 82.7%
  5. discard 2♦                         176.7 pts (exact), scores 100.0%
```

Four to the royal beats a made pair by 225 points a round, and it is worth
breaking the pair to chase it. `scores` is the chance of making *anything*,
which matters here because a round that scores nothing ends the game.

**Exact where exact is affordable, sampled where it is not.** Discarding one
card has 45 possible replacements and discarding two has 990, so those are
computed by enumerating every draw — they are not estimates. Five discards has
1,221,759, so that one is sampled. The two are not interchangeable and the
output labels which it used, because `(exact)` and `±136` are different kinds
of claim.

**The error bars are respected, not decorative.** With 400 trials, two options
whose expected scores differ by less than the combined sampling error are not
distinguishable, and printing them as 1st and 2nd would be reporting noise as a
finding. The advisor marks every option that ties with the leader:

```
  the top 3 are within sampling error of each other; any of them is a
  defensible choice
```

The bars are widest exactly where the payoff is most skewed — one 5000-point
straight flush in a 400-trial sample moves the mean a long way — which is a
property of the game, not a defect in the estimator. `--trials` narrows them.

A test cross-checks the sampled estimate against a full brute-force
enumeration of a three-card draw and requires it to land within four standard
errors. A Monte Carlo estimator with a subtle bias still produces
confident-looking output, which is the failure mode worth a test.

## Straights, which were missing entirely

A seven-card poker game with no straight and no straight flush is not a small
omission: **a straight is more likely than a flush**, so hands that should have
scored were scoring as nothing and ending the game.

Detecting one in seven cards is not a sort-and-scan, for two reasons.

**Duplicates have to be collapsed first.** A pair inside the run leaves only
six distinct ranks in seven cards, and a consecutive-pairs check over the
sorted list reads the repeat as a gap — so `5 6 6 7 8 9` looks like no
straight. Ranks go into a set before anything else happens.

**The ace counts twice, and cannot hold both values at once.** A-2-3-4-5 (the
"wheel") and 10-J-Q-K-A are both straights, so the ace is added at *both* ends
of the value set. Ranking purely by value would then make the wheel the highest
straight in the deck rather than the lowest, so it reports its high card as the
5 it runs up to. And the ace must not wrap: `K A 2 3 4` is not a straight,
which falls out of adding a second value rather than treating the sequence as
circular.

Straight flushes are checked **per suit**, which is the part that looks
redundant and isn't. "Has a straight and has a flush" is a different question:

```
5♥ 6♦ 7♥ 8♠ 9♥ K♥ 2♥
```

That hand contains a 5-6-7-8-9 straight and five hearts. It is not a straight
flush — no five-card selection is both — and it scores as a flush. Only cards
of a single suit can form one, so the search runs inside each suit.

## Layout

```
src/card_game/
  cards.py     Card, Suit, Deck          (no I/O)
  hand.py      Hand and the scorer       (pure)
  game.py      round and game state      (no I/O)
  advisor.py   discard evaluation        (pure)
  display.py   rich rendering, prompts   (the only module that prints)
  cli.py       entry point
```

The rules don't print and the display doesn't decide anything. That split is
what lets a test play twelve full rounds without a terminal.

## Two more scoring bugs this version fixes

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
