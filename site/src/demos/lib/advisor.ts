/**
 * Port of `card_game.advisor`, for the playable demo.
 *
 * The game asks which cards to throw away and gives the player nothing to
 * decide with. The choice is not obvious either: holding a pair and drawing
 * five is a completely different bet from holding four to a flush and drawing
 * three, and which is better depends on numbers nobody works out at the table.
 *
 * **Exact where exact is affordable, sampled where it is not.** Discarding one
 * card has 45 possible replacements and two has 990, so those are enumerated
 * and are not estimates. Five discards has 1,221,759, so that one is sampled.
 * The output says which, because `(exact)` and `±136` are different claims.
 *
 * The exact path is cross-checked against the Python in `ports.test.ts`. The
 * sampled path cannot be — a different RNG draws different cards — so it is
 * instead tested for convergence against full enumeration.
 */

import {
  type Card,
  type HandRank,
  type Rank,
  type Suit,
  HAND_SCORES,
  RANKS,
  SUITS,
  freshDeck,
  scoreCards,
} from "./cards";

/** Enumerate rather than sample while the number of draws is at most this. */
export const EXACT_LIMIT = 1_000;
export const DEFAULT_TRIALS = 400;
export const MAX_DISCARDS = 5;
/** Two sampled options tie within this many standard errors of each other. */
export const TIE_SIGMAS = 2;

export interface Outcome {
  positions: number[];
  expectedPoints: number;
  distribution: Partial<Record<HandRank, number>>;
  draws: number;
  exact: boolean;
  standardError: number;
  /** Chance of making anything at all — a round scoring nothing ends the game. */
  probabilityOfScoring: number;
}

function cardKey(card: Card): string {
  return `${card.rank}${card.suit}`;
}

/**
 * Every card the player has not seen.
 *
 * The hand is the only information available, so the unseen set is the deck
 * minus the hand. Drawing from a fresh deck that still held the player's own
 * cards would quietly overstate the chance of improving a pair.
 */
export function unseenCards(known: Card[]): Card[] {
  const held = new Set(known.map(cardKey));
  return freshDeck().filter((c) => !held.has(cardKey(c)));
}

function combinationCount(n: number, k: number): number {
  if (k < 0 || k > n) return 0;
  let out = 1;
  for (let i = 0; i < k; i++) out = (out * (n - i)) / (i + 1);
  return Math.round(out);
}

/** Every k-subset of `pool`, in the same order Python's `combinations` yields. */
function* combinations<T>(pool: T[], k: number): Generator<T[]> {
  if (k === 0) {
    yield [];
    return;
  }
  const indices = Array.from({ length: k }, (_, i) => i);
  while (true) {
    yield indices.map((i) => pool[i]);
    let i = k - 1;
    while (i >= 0 && indices[i] === i + pool.length - k) i--;
    if (i < 0) return;
    indices[i] += 1;
    for (let j = i + 1; j < k; j++) indices[j] = indices[j - 1] + 1;
  }
}

/** Draw `count` distinct cards, without replacement. */
function sampleWithout<T>(pool: T[], count: number, random: () => number): T[] {
  const copy = [...pool];
  const out: T[] = [];
  for (let i = 0; i < count; i++) {
    const j = i + Math.floor(random() * (copy.length - i));
    [copy[i], copy[j]] = [copy[j], copy[i]];
    out.push(copy[i]);
  }
  return out;
}

export function allDiscards(
  handSize: number,
  maxDiscards = MAX_DISCARDS,
): number[][] {
  const out: number[][] = [];
  const positions = Array.from({ length: handSize }, (_, i) => i);
  for (let size = 0; size <= Math.min(maxDiscards, handSize); size++) {
    for (const combo of combinations(positions, size)) out.push(combo);
  }
  return out;
}

export function evaluateDiscard(
  hand: Card[],
  positions: number[],
  trials = DEFAULT_TRIALS,
  random: () => number = Math.random,
  /** The unseen deck, if the caller already built it. Same for every option,
   *  so rebuilding 52 cards per discard was pure waste. */
  pool?: Card[],
): Outcome {
  const chosen = new Set(positions);
  for (const p of positions) {
    if (!(p >= 0 && p < hand.length)) throw new Error(`no card at position ${p}`);
  }
  if (chosen.size > MAX_DISCARDS) {
    throw new Error(`at most ${MAX_DISCARDS} cards may be discarded`);
  }

  const kept = hand.filter((_, i) => !chosen.has(i));
  const unseen = pool ?? unseenCards(hand);
  const count = chosen.size;

  const total = combinationCount(unseen.length, count);
  const exact = count === 0 || total <= EXACT_LIMIT;
  const draws: Iterable<Card[]> = exact
    ? combinations(unseen, count)
    : (function* () {
        for (let i = 0; i < trials; i++) yield sampleWithout(unseen, count, random);
      })();
  const evaluated = exact ? Math.max(1, total) : trials;

  const tally = new Map<HandRank, number>();
  let sum = 0;
  let sumSquares = 0;
  for (const drawn of draws) {
    const rank = scoreCards([...kept, ...drawn]);
    tally.set(rank, (tally.get(rank) ?? 0) + 1);
    const points = HAND_SCORES[rank];
    sum += points;
    sumSquares += points * points;
  }

  const mean = sum / evaluated;
  let standardError = 0;
  if (!exact && evaluated >= 2) {
    const variance = Math.max(0, sumSquares / evaluated - mean * mean);
    standardError = Math.sqrt(variance / evaluated);
  }

  const distribution: Partial<Record<HandRank, number>> = {};
  for (const [rankName, n] of tally) distribution[rankName] = n / evaluated;

  return {
    positions: [...positions].sort((a, b) => a - b),
    expectedPoints: mean,
    distribution,
    draws: evaluated,
    exact,
    standardError,
    probabilityOfScoring: 1 - (distribution.None ?? 0),
  };
}

/**
 * Every legal discard, ranked by expected points.
 *
 * Ties break towards discarding fewer cards: with nothing to choose between
 * two options, keeping more of a known hand is the smaller bet.
 */
export function bestDiscards(
  hand: Card[],
  trials = DEFAULT_TRIALS,
  top = 5,
  random: () => number = Math.random,
): Outcome[] {
  const pool = unseenCards(hand);
  const outcomes = allDiscards(hand.length).map((positions) =>
    evaluateDiscard(hand, positions, trials, random, pool),
  );
  outcomes.sort((a, b) => {
    if (a.expectedPoints !== b.expectedPoints) {
      return b.expectedPoints - a.expectedPoints;
    }
    if (a.positions.length !== b.positions.length) {
      return a.positions.length - b.positions.length;
    }
    const ax = a.positions.join(",");
    const bx = b.positions.join(",");
    return ax < bx ? -1 : ax > bx ? 1 : 0;
  });
  return outcomes.slice(0, top);
}

/**
 * Options indistinguishable from the leader.
 *
 * Sampling error is real and the honest answer is often "these three are the
 * same". Exact options tie only when their means are equal.
 */
export function statisticalTies(outcomes: Outcome[]): Outcome[] {
  if (outcomes.length === 0) return [];
  const leader = outcomes[0];
  const tied = [leader];
  for (const other of outcomes.slice(1)) {
    const margin =
      TIE_SIGMAS *
      Math.sqrt(leader.standardError ** 2 + other.standardError ** 2);
    if (leader.expectedPoints - other.expectedPoints <= margin) tied.push(other);
  }
  return tied;
}

/** `Ah`, `10s`, `Td`, `qc` → a card. */
export function parseCard(text: string): Card {
  const cleaned = text.trim().toLowerCase();
  if (cleaned.length < 2) throw new Error(`not a card: ${text}`);
  const suitChar = cleaned.slice(-1);
  const rankText = cleaned.slice(0, -1);
  const suit = SUITS.find((s) => s.startsWith(suitChar));
  if (!suit) throw new Error(`not a suit: ${suitChar} (use one of cdhs)`);
  const rank = (
    rankText === "t" ? "10" : RANKS.find((r) => r.toLowerCase() === rankText)
  ) as Rank | undefined;
  if (!rank) throw new Error(`not a rank: ${rankText}`);
  return { suit: suit as Suit, rank };
}
