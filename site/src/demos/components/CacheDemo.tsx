import { useCallback, useMemo, useState } from "react";

import { type CacheEvent, LruCache } from "../lib/lru";
import { Term } from "./Term";

const KEYS = ["a", "b", "c", "d", "e", "f"];
const CAPACITY = 4;

export function CacheDemo() {
  const [cache, setCache] = useState(() => new LruCache(CAPACITY));
  const [log, setLog] = useState<CacheEvent[]>([]);
  const [, bump] = useState(0);

  const call = useCallback(
    (key: string) => {
      const event = cache.call(key, (k) => k.toUpperCase());
      setLog((l) => [event, ...l].slice(0, 8));
      bump((n) => n + 1);
    },
    [cache],
  );

  const reset = useCallback(() => {
    const fresh = new LruCache(CAPACITY);
    setCache(fresh);
    setLog([]);
    bump((n) => n + 1);
  }, []);

  const order = cache.order;
  const stats = useMemo(
    () => ({ hits: cache.hits, misses: cache.misses, rate: cache.hitRate }),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [cache.hits, cache.misses, log],
  );

  return (
    <div className="demo">
      <div className="demo-controls">
        <div className="control">
          <span className="control-label">Call</span>
          {KEYS.map((k) => (
            <button key={k} className="chip mono" onClick={() => call(k)}>
              {k}
            </button>
          ))}
        </div>
        <button className="chip" onClick={reset}>
          Reset
        </button>
        <span className="demo-hint">
          <Term id="lru" /> decides what gets <Term id="eviction">evicted</Term>{" "}
          when the <Term id="cache" /> is full.
        </span>
      </div>

      <div className="lru-track">
        <div className="lru-labels">
          <span>least recently used</span>
          <span>most recently used</span>
        </div>
        <div className="lru-slots">
          {Array.from({ length: CAPACITY }).map((_, i) => {
            const key = order[i];
            return (
              <div key={i} className={`lru-slot${key ? " filled" : ""}`}>
                {key ? <code>{key}</code> : <span className="muted">empty</span>}
              </div>
            );
          })}
        </div>
      </div>

      <div className="metric-row">
        <div className="metric">
          <div className="metric-label"><Term id="hit-rate">Hits</Term></div>
          <div className="metric-value" style={{ color: "var(--se)" }}>{stats.hits}</div>
        </div>
        <div className="metric">
          <div className="metric-label"><Term id="hit-rate">Misses</Term></div>
          <div className="metric-value" style={{ color: "var(--ds)" }}>{stats.misses}</div>
        </div>
        <div className="metric">
          <div className="metric-label"><Term id="hit-rate">Hit rate</Term></div>
          <div className="metric-value">{(stats.rate * 100).toFixed(0)}%</div>
        </div>
        <div className="metric">
          <div className="metric-label"><Term id="capacity">Capacity</Term></div>
          <div className="metric-value">{CAPACITY}</div>
        </div>
      </div>

      {log.length > 0 && (
        <ol className="lru-log">
          {log.map((event, i) => (
            <li key={`${event.key}-${i}`}>
              <code>{event.key}</code>
              <span className={event.outcome === "hit" ? "tag-hit" : "tag-miss"}>
                {event.outcome}
              </span>
              {event.evicted && (
                <span className="tag-evict">evicted {event.evicted}</span>
              )}
              <span className="muted mono">[{event.order.join(" ")}]</span>
            </li>
          ))}
        </ol>
      )}

      <p className="demo-note">
        This demo runs <Term id="lru" />. The project also implements{" "}
        <Term id="lfu" /> and <Term id="ttl" /> expiry, and benchmarks the two
        policies against each other — neither wins on every workload.
      </p>
      <p className="demo-note">
        Press the same key twice for a hit — notice it jumps to the most-recent end, which
        is what protects it from the next eviction. Fill past {CAPACITY} entries and the
        leftmost key is evicted. Recency lives in the map's insertion order, so moving a
        key is O(1); the original kept a list and scanned it on every hit, which is the
        one path a cache exists to make fast.
      </p>
    </div>
  );
}
