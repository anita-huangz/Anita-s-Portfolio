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
  | "4Kind" | "FullHouse" | "Flush" | "3Kind" | "2Pair" | "Pair" | "None";

export const HAND_SCORES: Record<HandRank, number> = {
  "4Kind": 2000,
  FullHouse: 250,
  Flush: 200,
  "3Kind": 100,
  "2Pair": 50,
  Pair: 10,
  None: 0,
};

export const HAND_SIZE = 7;
export const MAX_DISCARDS = 5;

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

  if (rankGroups[0] >= 4) return "4Kind";
  if (rankGroups[0] >= 3 && rankGroups.length > 1 && rankGroups[1] >= 2) {
    return "FullHouse";
  }
  if (Math.max(...suitGroups) >= 5) return "Flush";
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
