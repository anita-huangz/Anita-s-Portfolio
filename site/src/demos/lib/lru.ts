/**
 * Port of `fastcache.lru`, for the eviction visualisation.
 *
 * Recency lives in the Map's insertion order -- `delete` then `set` moves a
 * key to most-recently-used in O(1), and the first key is the LRU victim. The
 * Python it mirrors used a list and paid O(n) on every hit.
 */

export interface CacheEvent {
  key: string;
  outcome: "hit" | "miss";
  evicted: string | null;
  /** Keys after the call, oldest first. */
  order: string[];
}

export class LruCache {
  private readonly store = new Map<string, unknown>();
  hits = 0;
  misses = 0;

  constructor(readonly maxSize: number) {
    if (maxSize < 0) throw new Error("maxSize must be non-negative");
  }

  get size(): number {
    return this.store.size;
  }

  /** Keys in LRU order, oldest first. */
  get order(): string[] {
    return [...this.store.keys()];
  }

  get hitRate(): number {
    const total = this.hits + this.misses;
    return total === 0 ? 0 : this.hits / total;
  }

  /** Look up a key, computing it on a miss. Returns what happened. */
  call(key: string, compute: (key: string) => unknown): CacheEvent {
    if (this.store.has(key)) {
      this.hits += 1;
      const value = this.store.get(key)!;
      this.store.delete(key);
      this.store.set(key, value);
      return { key, outcome: "hit", evicted: null, order: this.order };
    }

    this.misses += 1;
    if (this.maxSize === 0) {
      return { key, outcome: "miss", evicted: null, order: this.order };
    }

    this.store.set(key, compute(key));
    let evicted: string | null = null;
    if (this.store.size > this.maxSize) {
      evicted = this.store.keys().next().value ?? null;
      if (evicted !== null) this.store.delete(evicted);
    }
    return { key, outcome: "miss", evicted, order: this.order };
  }

  clear(): void {
    this.store.clear();
    this.hits = 0;
    this.misses = 0;
  }
}
