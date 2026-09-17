import { useMemo, useState } from "react";

import indexData from "../../data/demos/search-index.json";
import golden from "../../data/demos/trie-golden.json";
import { Trie, buildIndex, characterToKey, searchIndex } from "../lib/trie";

const WORDS = golden.words;

const INDEX = buildIndex(indexData.postings, indexData.lengths);
const EXCERPTS = indexData.excerpts as Record<string, string>;
const PAGE_COUNT = Object.keys(indexData.lengths).length;

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

  // The second half of the project: the trie says which words look like the
  // query, and BM25 says which pages those words make relevant.
  const [searchQuery, setSearchQuery] = useState("park hours");
  const [requireAll, setRequireAll] = useState(true);
  const hits = useMemo(
    () => searchIndex(INDEX, searchQuery, requireAll),
    [searchQuery, requireAll],
  );
  const topScore = hits.length > 0 ? hits[0].score : 1;

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

      <div className="rank-panel">
        <h5 className="demo-h">
          Ranked search over a {PAGE_COUNT}-page crawl
        </h5>
        <div className="demo-controls">
          <label className="control" style={{ flex: 1 }}>
            <input
              className="demo-input"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="words, par* for a prefix, d?g for a wildcard"
              spellCheck={false}
            />
          </label>
          <div className="control">
            {["park", "park hours", "par*", "d?g", "dog park"].map((q) => (
              <button
                key={q}
                className="chip mono"
                aria-pressed={searchQuery === q}
                onClick={() => setSearchQuery(q)}
              >
                {q}
              </button>
            ))}
            <button
              className="chip"
              aria-pressed={requireAll}
              onClick={() => setRequireAll((v) => !v)}
              title="Require every query token, rather than any of them"
            >
              AND
            </button>
          </div>
        </div>

        {hits.length === 0 ? (
          <p className="demo-note">
            Nothing matched. With <strong>AND</strong> on, a single token that
            matches no page means the query can never be satisfied — so it
            returns nothing rather than the pages that matched the other word.
          </p>
        ) : (
          <ol className="hit-list">
            {hits.map((hit, i) => (
              <li key={hit.url}>
                <div className="hit-head">
                  <span className="hit-rank">{i + 1}</span>
                  <code className="hit-url">{hit.url}</code>
                  <span className="hit-score">{hit.score.toFixed(3)}</span>
                </div>
                <div className="hit-bar">
                  <span style={{ width: `${(hit.score / topScore) * 100}%` }} />
                </div>
                <div className="hit-terms">
                  {Object.entries(hit.matched)
                    .sort((a, b) => b[1] - a[1])
                    .map(([term, count]) => (
                      <span className="hit-term" key={term}>
                        {term} &times;{count}
                      </span>
                    ))}
                  <span className="hit-len">
                    {indexData.lengths[hit.url as keyof typeof indexData.lengths]} words
                  </span>
                </div>
                <p className="hit-excerpt">{EXCERPTS[hit.url]}</p>
              </li>
            ))}
          </ol>
        )}
        <p className="demo-note">
          The index used to map each word to the <em>set</em> of pages holding
          it, and return that set alphabetically — retrieval without ranking. A
          page mentioning "park" once and a park directory mentioning it
          nineteen times were indistinguishable. BM25 needs three things the set
          could not provide: how often a term appears, how long the page is, and
          how many pages contain the term at all.{" "}
          <strong>Try "park":</strong> <code>/park-hours</code> beats{" "}
          <code>/dog-park-rules</code> despite saying it fewer times, because 4
          in 32 words is denser than 5 in 64.
        </p>
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
