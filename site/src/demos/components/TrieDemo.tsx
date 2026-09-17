import { useMemo, useState } from "react";

import golden from "../../data/demos/trie-golden.json";
import { Trie, characterToKey } from "../lib/trie";

const WORDS = golden.words;

export function TrieDemo() {
  const [query, setQuery] = useState("par");
  const trie = useMemo(() => new Trie(Object.fromEntries(WORDS.map((w) => [w, w]))), []);

  const isWildcard = query.includes("?");
  const matches = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return [...trie.keys()];
    return isWildcard
      ? [...trie.wildcardSearch(q)].map(([k]) => k)
      : [...trie.keysWithPrefix(q)];
  }, [query, trie, isWildcard]);

  // The path the query walks, for highlighting. A wildcard branches, so only
  // the literal prefix before the first '?' is a single path.
  const literalPrefix = query.split("?")[0].toLowerCase();
  const pathDepth = useMemo(() => {
    let node = trie.root;
    let depth = 0;
    for (const char of literalPrefix) {
      const child = node.children.get(characterToKey(char));
      if (!child) break;
      node = child;
      depth += 1;
    }
    return depth;
  }, [literalPrefix, trie]);

  const matched = new Set(matches);

  return (
    <div className="demo">
      <div className="demo-controls">
        <label className="control" style={{ flex: 1 }}>
          <span className="control-label">Query</span>
          <input
            className="demo-input"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="prefix, or use ? as a single-character wildcard"
            spellCheck={false}
          />
        </label>
        <div className="control">
          {["par", "c?t", "tri", "??", "se"].map((q) => (
            <button key={q} className="chip" aria-pressed={query === q} onClick={() => setQuery(q)}>
              {q}
            </button>
          ))}
        </div>
      </div>

      <div className="demo-split">
        <div>
          <h5 className="demo-h">
            {isWildcard ? "Wildcard match" : "Prefix match"} — {matches.length} of {WORDS.length}
          </h5>
          <div className="wordcloud">
            {WORDS.map((w) => (
              <span key={w} className={`word${matched.has(w) ? " hit" : ""}`}>
                {matched.has(w) && !isWildcard && literalPrefix ? (
                  <>
                    <mark>{w.slice(0, literalPrefix.length)}</mark>
                    {w.slice(literalPrefix.length)}
                  </>
                ) : (
                  w
                )}
              </span>
            ))}
          </div>
        </div>

        <div>
          <h5 className="demo-h">Walk</h5>
          <ol className="walk">
            <li className="walk-step done">
              root <span className="walk-note">{WORDS.length} keys below</span>
            </li>
            {[...literalPrefix].map((char, i) => {
              const reached = i < pathDepth;
              return (
                <li key={i} className={`walk-step${reached ? " done" : " dead"}`}>
                  <code>{char}</code>
                  <span className="walk-note">
                    {reached
                      ? `child ${characterToKey(char)}${characterToKey(char) === 26 ? " (other)" : ""}`
                      : "no such child — dead end"}
                  </span>
                </li>
              );
            })}
            {isWildcard && (
              <li className="walk-step branch">
                <code>?</code>
                <span className="walk-note">branches across every child</span>
              </li>
            )}
          </ol>
          <p className="demo-note" style={{ marginTop: 12 }}>
            Each node has 27 children: one per letter, plus one bucket for everything
            else. That folding is why the trie is case-insensitive, and why a wildcard
            is a bounded walk rather than a scan of every key.
          </p>
        </div>
      </div>
    </div>
  );
}
