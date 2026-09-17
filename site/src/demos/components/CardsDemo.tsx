import { useCallback, useMemo, useState } from "react";

import {
  type Outcome,
  bestDiscards,
  statisticalTies,
} from "../lib/advisor";
import {
  type Card,
  type HandRank,
  HAND_SCORES,
  HAND_SIZE,
  MAX_DISCARDS,
  SUIT_SYMBOL,
  freshDeck,
  mulberry32,
  scoreCards,
  shuffle,
  suitColor,
} from "../lib/cards";

interface State {
  deck: Card[];
  hand: Card[];
  selected: Set<number>;
  phase: "discard" | "scored";
  rank: HandRank | null;
  rounds: HandRank[];
}

function deal(deck: Card[]): { hand: Card[]; rest: Card[] } {
  return { hand: deck.slice(0, HAND_SIZE), rest: deck.slice(HAND_SIZE) };
}

function newGame(seed: number): State {
  const { hand, rest } = deal(shuffle(freshDeck(), mulberry32(seed)));
  return { deck: rest, hand, selected: new Set(), phase: "discard", rank: null, rounds: [] };
}

export function CardsDemo() {
  const [state, setState] = useState<State>(() => newGame(Date.now() % 100000));

  const toggle = useCallback((i: number) => {
    setState((s) => {
      if (s.phase !== "discard") return s;
      const selected = new Set(s.selected);
      if (selected.has(i)) selected.delete(i);
      else if (selected.size < MAX_DISCARDS) selected.add(i);
      return { ...s, selected };
    });
  }, []);

  const draw = useCallback(() => {
    setState((s) => {
      const kept = s.hand.filter((_, i) => !s.selected.has(i));
      const needed = HAND_SIZE - kept.length;
      const hand = [...kept, ...s.deck.slice(0, needed)];
      const rank = scoreCards(hand);
      return {
        deck: s.deck.slice(needed),
        hand,
        selected: new Set(),
        phase: "scored",
        rank,
        rounds: rank === "None" ? s.rounds : [...s.rounds, rank],
      };
    });
  }, []);

  const nextRound = useCallback(() => {
    setState((s) => {
      const deck = s.deck.length >= HAND_SIZE ? s.deck : shuffle(freshDeck(), mulberry32(Date.now() % 99991));
      const { hand, rest } = deal(deck);
      return { deck: rest, hand, selected: new Set(), phase: "discard", rank: null, rounds: s.rounds };
    });
  }, []);

  const total = state.rounds.reduce((sum, r) => sum + HAND_SCORES[r], 0);

  const [showAdvice, setShowAdvice] = useState(false);
  // 250 trials keeps the click responsive; the one- and two-card discards are
  // enumerated regardless, so the cheap answers are also the exact ones. Even
  // so this is ~44,000 hand evaluations, which is why scoreCards counts suits
  // before looking for a straight flush.
  const advice = useMemo(
    () =>
      showAdvice && state.phase === "discard"
        ? bestDiscards(state.hand, 250, 4, mulberry32(state.hand.length * 7919))
        : [],
    [showAdvice, state.hand, state.phase],
  );
  const tiedSet = useMemo(
    () => new Set(statisticalTies(advice).map((o: Outcome) => advice.indexOf(o))),
    [advice],
  );
  const preview = scoreCards(state.hand);

  return (
    <div className="demo">
      <div className="hand">
        {state.hand.map((card, i) => (
          <button
            key={`${card.rank}${card.suit}${i}`}
            className={`playing-card${state.selected.has(i) ? " selected" : ""}`}
            onClick={() => toggle(i)}
            disabled={state.phase !== "discard"}
            aria-pressed={state.selected.has(i)}
            aria-label={`${card.rank} of ${card.suit}${state.selected.has(i) ? ", marked to discard" : ""}`}
          >
            <span className={`pip ${suitColor(card.suit)}`}>
              {card.rank}
              {SUIT_SYMBOL[card.suit]}
            </span>
          </button>
        ))}
      </div>

      {state.phase === "discard" && (
        <div className="advice-panel">
          <div className="advice-head">
            <h5 className="demo-h" style={{ margin: 0 }}>
              What should you throw?
            </h5>
            <button
              className="chip"
              aria-pressed={showAdvice}
              onClick={() => setShowAdvice((v) => !v)}
            >
              {showAdvice ? "hide" : "advise me"}
            </button>
          </div>
          {showAdvice && advice.length > 0 && (
            <>
              <ol className="advice-list">
                {advice.map((option, i) => (
                  <li
                    key={option.positions.join() || "none"}
                    className={`advice-row${tiedSet.has(i) ? " tied" : ""}`}
                  >
                    <button
                      className="advice-apply"
                      onClick={() =>
                        setState((cur) => ({
                          ...cur,
                          selected: new Set(option.positions),
                        }))
                      }
                      title="Mark these cards to discard"
                    >
                      {option.positions.length === 0
                        ? "keep all 7"
                        : option.positions
                            .map(
                              (pos) =>
                                `${state.hand[pos].rank}${SUIT_SYMBOL[state.hand[pos].suit]}`,
                            )
                            .join(" ")}
                    </button>
                    <span className="advice-points">
                      {option.expectedPoints.toFixed(1)} pts
                    </span>
                    <span className="advice-kind">
                      {option.exact
                        ? `exact, ${option.draws.toLocaleString()} draws`
                        : `±${(2 * option.standardError).toFixed(0)}, ${option.draws} samples`}
                    </span>
                    <span className="advice-scores">
                      scores {(option.probabilityOfScoring * 100).toFixed(0)}%
                    </span>
                  </li>
                ))}
              </ol>
              <p className="demo-note">
                {tiedSet.size > 1 ? (
                  <>
                    The top {tiedSet.size} are within sampling error of each
                    other, so any of them is a defensible choice — presenting
                    them as 1st and 2nd would be reporting noise as a finding.
                  </>
                ) : (
                  <>A clear winner: the gap is larger than the sampling error.</>
                )}{" "}
                One and two-card discards are <strong>enumerated</strong> — 45
                and 990 possible draws, so those are not estimates. Five
                discards is 1,221,759, so that one is sampled and says so.
              </p>
            </>
          )}
        </div>
      )}

      <div className="demo-controls">
        {state.phase === "discard" ? (
          <>
            <button className="chip primary" onClick={draw}>
              {state.selected.size === 0
                ? "Keep all 7"
                : `Discard ${state.selected.size} and draw`}
            </button>
            <span className="demo-hint">
              Click up to {MAX_DISCARDS} cards to discard. Current hand scores{" "}
              <strong>{preview}</strong> ({HAND_SCORES[preview]}).
            </span>
          </>
        ) : (
          <>
            <button className="chip primary" onClick={nextRound}>
              Next round
            </button>
            <span className="demo-hint">
              {state.rank === "None" ? (
                <>No scoring hand — in the real game that ends the run.</>
              ) : (
                <>
                  Scored <strong>{state.rank}</strong> for {HAND_SCORES[state.rank!]} points.
                </>
              )}
            </span>
          </>
        )}
      </div>

      <div className="metric-row">
        <div className="metric">
          <div className="metric-label">Rounds scored</div>
          <div className="metric-value">{state.rounds.length}</div>
        </div>
        <div className="metric">
          <div className="metric-label">Total</div>
          <div className="metric-value">{total}</div>
        </div>
        <div className="metric">
          <div className="metric-label">Cards left</div>
          <div className="metric-value">{state.deck.length}</div>
        </div>
      </div>

      <p className="demo-note">
        Scored by the same rules as the Python, checked against 400 hands it
        scored. All seven cards count, so a flush needs five of a suit anywhere
        in the hand — the original missed six- and seven-card flushes entirely,
        and scored two triples as three-of-a-kind rather than a full house.
        Straights were missing altogether, which matters because a straight is{" "}
        <em>more likely</em> than a flush: hands that should have scored were
        ending the run. A-2-3-4-5 counts and K-A-2-3-4 does not, and a straight
        flush is checked per suit — a hand can hold a straight and a flush
        without any five cards being both.
      </p>
    </div>
  );
}
