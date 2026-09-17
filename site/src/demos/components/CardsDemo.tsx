import { useCallback, useState } from "react";

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
        Scored by the same rules as the Python, checked against 400 hands it scored.
        All seven cards count, so a flush needs five of a suit anywhere in the hand —
        the original missed six- and seven-card flushes entirely, and scored two
        triples as three-of-a-kind rather than a full house.
      </p>
    </div>
  );
}
