/**
 * Port of `card_game.hand.score_cards` and the deck, for the playable demo.
 * Checked against 400 golden hands scored by the Python in `cards.test.ts`.
 */

export const RANKS = [
  "2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K", "A",
] as const;
export const SUITS = ["clubs", "diamonds", "hearts", "spades"] as const;

export type Rank = (typeof RANKS)[number];
export type Suit = (typeof SUITS)[number];

export interface Card {
  suit: Suit;
  rank: Rank;
}

export const SUIT_SYMBOL: Record<Suit, string> = {
  clubs: "♣",
  diamonds: "♦",
  hearts: "♥",
  spades: "♠",
};

export function suitColor(suit: Suit): "black" | "red" {
  return suit === "clubs" || suit === "spades" ? "black" : "red";
}

export type HandRank =
  | "StraightFlush" | "4Kind" | "FullHouse" | "Flush" | "Straight"
  | "3Kind" | "2Pair" | "Pair" | "None";

export const HAND_SCORES: Record<HandRank, number> = {
  StraightFlush: 5000,
  "4Kind": 2000,
  FullHouse: 250,
  Flush: 200,
  Straight: 150,
  "3Kind": 100,
  "2Pair": 50,
  Pair: 10,
  None: 0,
};

export const HAND_SIZE = 7;
export const MAX_DISCARDS = 5;

/** Aces high. The ace's low value is handled in `straightHigh`. */
export const RANK_VALUES: Record<Rank, number> = Object.fromEntries(
  RANKS.map((rank, i) => [rank, i + 2]),
) as Record<Rank, number>;

const VALUE_RANKS = new Map<number, Rank>(
  RANKS.map((rank, i) => [i + 2, rank]),
);

const ACE_VALUE = RANK_VALUES.A;
const ACE_LOW = 1;
const STRAIGHT_LENGTH = 5;

/**
 * Highest card of the best straight, or null.
 *
 * Ranks go into a set first: a pair inside the run leaves six distinct ranks
 * in seven cards, and a consecutive-pairs check over the sorted list would
 * read the repeat as a gap. The ace is then added at *both* ends, because
 * A-2-3-4-5 and 10-J-Q-K-A are both straights and one value cannot serve both
 * — while `K A 2 3 4` stays a non-straight, which is why this is a second
 * value rather than a circular sequence.
 */
export function straightHigh(cards: Card[]): Rank | null {
  const values = new Set(cards.map((c) => RANK_VALUES[c.rank]));
  if (values.has(ACE_VALUE)) values.add(ACE_LOW);

  for (const high of [...values].sort((a, b) => b - a)) {
    let run = true;
    for (let offset = 0; offset < STRAIGHT_LENGTH; offset++) {
      if (!values.has(high - offset)) {
        run = false;
        break;
      }
    }
    // A straight's high value is at least 5, so the wheel reports the 5 it
    // runs up to — which is also what ranks it below every other straight.
    if (run) return VALUE_RANKS.get(high) ?? null;
  }
  return null;
}

/**
 * Highest card of the best straight flush, or null.
 *
 * Per suit, which is the point: "has a straight and has a flush" is a
 * different question, and seven cards can hold both without any five of them
 * being a straight flush.
 */
export function straightFlushHigh(cards: Card[]): Rank | null {
  // Count suits first and bail if none can hold five. This is the hot path:
  // the discard advisor scores tens of thousands of hands per click, and
  // allocating four filtered arrays for a hand that obviously has no flush
  // was most of that time — 2.6s of frozen page per click, down to 65ms.
  //
  // Worth noting that the same change in the Python is *not* a win (259ms
  // before, 277ms after): building the Counter costs about what the
  // dict-of-lists it replaces did, and interpreter overhead dominates either
  // way. The Python keeps the simpler shape. Same logic, different hot spots
  // — which is why this was measured on both sides rather than assumed.
  const bySuit = new Map<Suit, number>();
  for (const card of cards) {
    bySuit.set(card.suit, (bySuit.get(card.suit) ?? 0) + 1);
  }
  let possible = false;
  for (const n of bySuit.values()) {
    if (n >= STRAIGHT_LENGTH) {
      possible = true;
      break;
    }
  }
  if (!possible) return null;

  let bestValue: number | null = null;
  let bestRank: Rank | null = null;
  for (const suit of SUITS) {
    if ((bySuit.get(suit) ?? 0) < STRAIGHT_LENGTH) continue;
    const suited = cards.filter((c) => c.suit === suit);
    const high = straightHigh(suited);
    if (high === null) continue;
    const value = RANK_VALUES[high];
    if (bestValue === null || value > bestValue) {
      bestValue = value;
      bestRank = high;
    }
  }
  return bestRank;
}

function counts<T extends string>(values: T[]): number[] {
  const tally = new Map<T, number>();
  for (const v of values) tally.set(v, (tally.get(v) ?? 0) + 1);
  return [...tally.values()];
}

/**
 * Best rank the cards make.
 *
 * The two comparisons that matter are `>=`, not `===`. In a seven-card hand a
 * flush can be six or seven cards, and a full house can be two triples; the
 * Python originally tested for exact counts and missed both.
 */
export function scoreCards(cards: Card[]): HandRank {
  if (cards.length === 0) return "None";

  const rankGroups = counts(cards.map((c) => c.rank)).sort((a, b) => b - a);
  const suitGroups = counts(cards.map((c) => c.suit));

  if (straightFlushHigh(cards) !== null) return "StraightFlush";
  if (rankGroups[0] >= 4) return "4Kind";
  if (rankGroups[0] >= 3 && rankGroups.length > 1 && rankGroups[1] >= 2) {
    return "FullHouse";
  }
  if (Math.max(...suitGroups) >= 5) return "Flush";
  if (straightHigh(cards) !== null) return "Straight";
  if (rankGroups[0] >= 3) return "3Kind";
  if (rankGroups.filter((n) => n >= 2).length >= 2) return "2Pair";
  if (rankGroups[0] >= 2) return "Pair";
  return "None";
}

/** A small deterministic PRNG, so a shuffle can be reproduced from a seed. */
export function mulberry32(seed: number): () => number {
  let a = seed >>> 0;
  return () => {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

export function freshDeck(): Card[] {
  return SUITS.flatMap((suit) => RANKS.map((rank) => ({ suit, rank })));
}

export function shuffle<T>(items: T[], random: () => number): T[] {
  const out = [...items];
  for (let i = out.length - 1; i > 0; i--) {
    const j = Math.floor(random() * (i + 1));
    [out[i], out[j]] = [out[j], out[i]];
  }
  return out;
}
