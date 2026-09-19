import { useMemo, useState } from "react";

import golden from "../../data/demos/text-golden.json";
import {
  type BuiltIndex,
  buildFromDocuments,
  characterToKey,
  searchBuilt,
} from "../lib/trie";
import { Term } from "./Term";

/** The bundled pages, as editable text. */
const SEED = Object.entries(golden.seed as Record<string, string>)
  .map(([url, text]) => `${url}\n${text}`)
  .join("\n\n");

const EXAMPLES: { label: string; text: string }[] = [
  { label: "Parks site", text: SEED },
  {
    label: "Recipes",
    text: [
      "/bread\nMix flour, water, salt and yeast. Knead the dough until smooth, " +
        "then prove it for two hours. Bake at 230C for thirty minutes.",
      "/pasta\nMix flour and eggs into a dough. Rest the dough, roll it thin, " +
        "and cut it into ribbons. Boil for three minutes.",
      "/pizza\nProve the dough slowly. Roll it thin, top it, and bake it as hot " +
        "as the oven goes. The dough is the whole thing.",
    ].join("\n\n"),
  },
  {
    label: "One-line docs",
    text: [
      "/a\nthe quick brown fox jumps over the lazy dog",
      "/b\nthe dog barked and the fox ran",
      "/c\nquick quick quick brown brown fox",
    ].join("\n\n"),
  },
];

/**
 * Split pasted text into documents.
 *
 * A blank line starts a new document. If its first line looks like a label —
 * short, no spaces — it becomes the name; otherwise the document is numbered.
 * Forgiving on purpose: someone pasting three paragraphs should get three
 * documents without reading instructions.
 */
function parseDocuments(text: string): Record<string, string> {
  const blocks = text.split(/\n\s*\n/).map((b) => b.trim()).filter(Boolean);
  const out: Record<string, string> = {};
  blocks.forEach((block, i) => {
    const [first, ...rest] = block.split("\n");
    const looksLikeLabel = rest.length > 0 && first.length < 40 && !/\s/.test(first.trim());
    const label = looksLikeLabel ? first.trim() : `doc-${i + 1}`;
    const body = looksLikeLabel ? rest.join("\n") : block;
    // Two blocks with the same label would silently overwrite each other.
    let unique = label;
    let n = 2;
    while (unique in out) unique = `${label} (${n++})`;
    out[unique] = body;
  });
  return out;
}

export function TrieDemo() {
  const [corpus, setCorpus] = useState(SEED);
  const [stemming, setStemming] = useState(false);
  const [searchQuery, setSearchQuery] = useState("park hours");
  const [requireAll, setRequireAll] = useState(true);
  const [query, setQuery] = useState("par");

  const documents = useMemo(() => parseDocuments(corpus), [corpus]);
  const index: BuiltIndex = useMemo(
    () => buildFromDocuments(documents, stemming),
    [documents, stemming],
  );

  const terms = useMemo(() => Object.keys(index.postings).sort(), [index]);
  const hits = useMemo(
    () => searchBuilt(index, searchQuery, requireAll),
    [index, searchQuery, requireAll],
  );
  const topScore = hits.length > 0 ? hits[0].score : 1;

  const isPhrase = searchQuery.trim().startsWith('"');
  const isWildcard = query.includes("?");
  const literalPrefix = query.split("?")[0].toLowerCase();

  const matches = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return terms;
    return isWildcard
      ? [...index.trie.wildcardSearch(q)].map(([k]) => k)
      : [...index.trie.keysWithPrefix(q)];
  }, [query, index, isWildcard, terms]);
  const matched = new Set(matches);

  const pathDepth = useMemo(() => {
    let node = index.trie.root;
    let depth = 0;
    for (const char of literalPrefix) {
      const child = node.children.get(characterToKey(char));
      if (!child) break;
      node = child;
      depth += 1;
    }
    return depth;
  }, [literalPrefix, index]);

  // A word cloud of ten thousand terms is not a visualisation.
  const shown = terms.slice(0, 220);

  return (
    <div className="demo">
      <h5 className="demo-h">Your corpus</h5>
      <p className="demo-hint" style={{ margin: "0 0 8px" }}>
        Paste anything. A blank line starts a new document; if its first line is
        a single word it becomes the label. Everything below is built from this
        text in your browser. The command line <Term id="crawler">crawls</Term>
        a live site instead — point it at any URL — but a static page cannot, so
        here you bring the text.
      </p>
      <textarea
        className="demo-input"
        style={{ minHeight: 120, fontFamily: "var(--mono)", fontSize: 12.5 }}
        value={corpus}
        spellCheck={false}
        onChange={(e) => setCorpus(e.target.value)}
        aria-label="Documents to index"
      />
      <div className="demo-controls">
        <div className="control" role="group" aria-label="Example corpora">
          <span className="control-label">Load</span>
          {EXAMPLES.map((e) => (
            <button
              key={e.label}
              className="chip"
              aria-pressed={corpus === e.text}
              onClick={() => setCorpus(e.text)}
            >
              {e.label}
            </button>
          ))}
        </div>
        <div className="control" role="group" aria-label="Index options">
          <button
            className="chip"
            aria-pressed={stemming}
            onClick={() => setStemming((v) => !v)}
            title="Fold words to Porter stems, so 'parks' finds 'park'"
          >
            Stemming
          </button>
        </div>
      </div>
      <div className="metric-row">
        <Stat label="Documents" value={String(Object.keys(documents).length)} />
        <Stat label="Words" value={index.tokens.toLocaleString()} />
        <Stat
          label={stemming ? "Distinct stems" : "Distinct words"}
          value={terms.length.toLocaleString()}
        />
      </div>

      <div className="rank-panel">
        <h5 className="demo-h">Ranked search</h5>
        <p className="demo-hint" style={{ margin: "0 0 10px" }}>
          Ranked by <Term id="bm25" />. <Term id="and">AND</Term> requires every
          word; a <Term id="wildcard" /> searches a pattern;{" "}
          <strong>"quoted words"</strong> require the phrase, adjacent and in
          order.
        </p>
        <div className="demo-controls">
          <label className="control" style={{ flex: 1 }}>
            <input
              className="demo-input"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder='words, "a phrase", par* for a prefix, d?g for a wildcard'
              spellCheck={false}
              aria-label="Search query"
            />
          </label>
          <div className="control">
            {["park", "dog park", '"dog park"', "par*", "d?g"].map((q) => (
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
              disabled={isPhrase}
            >
              AND
            </button>
          </div>
        </div>

        {hits.length === 0 ? (
          <p className="demo-note">
            {isPhrase ? (
              <>
                No document contains that phrase. A phrase needs the words{" "}
                <em>adjacent and in order</em> — drop the quotes to find
                documents that merely contain all of them.
              </>
            ) : (
              <>
                Nothing matched. With <strong>AND</strong> on, a single token
                that matches no document means the query can never be satisfied
                — so it returns nothing rather than the documents that matched
                the other word.
              </>
            )}
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
                        {stemming && index.surfaces[term]?.length > 1 && (
                          <em className="hit-surfaces">
                            {" "}
                            ({index.surfaces[term].join(", ")})
                          </em>
                        )}
                      </span>
                    ))}
                  <span className="hit-len">
                    {index.corpus.lengths[hit.url]} words
                  </span>
                </div>
                <p className="hit-excerpt">
                  {(documents[hit.url] ?? "").slice(0, 170)}
                  {(documents[hit.url] ?? "").length > 170 ? "…" : ""}
                </p>
              </li>
            ))}
          </ol>
        )}
        <p className="demo-note">
          The index used to map each word to the <em>set</em> of documents
          holding it, returned alphabetically — retrieval without ranking. BM25
          needs three things a set cannot provide: how often a term appears, how
          long the document is, and how many documents contain it at all. On the
          bundled pages, searching <code>park</code> puts{" "}
          <code>/park-hours</code> above <code>/dog-park-rules</code> despite
          fewer mentions, because 4 in 32 words is denser than 5 in 64.{" "}
          <strong>
            Compare <code>dog park</code> with <code>"dog park"</code>
          </strong>{" "}
          — the first finds two pages, the second one, because the directory
          mentions dogs and parks without ever putting the words together.{" "}
          {stemming ? (
            <>
              With stemming on, <code>parks</code> and <code>parking</code> fold
              onto <code>park</code>, so one query finds all three.
            </>
          ) : (
            <>
              Turn on <strong>Stemming</strong> and search <code>parks</code> —
              without it, that is a different word from <code>park</code>.
            </>
          )}
        </p>
      </div>

      <div className="demo-controls" style={{ marginTop: 18 }}>
        <label className="control" style={{ flex: 1 }}>
          <span className="control-label">Explore the index</span>
          <input
            className="demo-input"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="prefix, or use ? as a single-character wildcard"
            spellCheck={false}
            aria-label="Prefix or wildcard to explore"
          />
        </label>
        <div className="control">
          {["par", "c?t", "do", "??", "th"].map((q) => (
            <button
              key={q}
              className="chip mono"
              aria-pressed={query === q}
              onClick={() => setQuery(q)}
            >
              {q}
            </button>
          ))}
        </div>
      </div>

      <div className="demo-split">
        <div>
          <h5 className="demo-h">
            {isWildcard ? "Wildcard match" : "Prefix match"} — {matches.length} of{" "}
            {terms.length}
          </h5>
          <div className="wordcloud">
            {shown.map((w) => (
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
          {terms.length > shown.length && (
            <p className="demo-hint">
              Showing the first {shown.length} of {terms.length} terms.
            </p>
          )}
        </div>

        <div>
          <h5 className="demo-h">
            Walk down the <Term id="trie" />
          </h5>
          <ol className="walk">
            <li className="walk-step done">
              root <span className="walk-note">{terms.length} keys below</span>
            </li>
            {[...literalPrefix].map((char, i) => {
              const reached = i < pathDepth;
              return (
                <li key={i} className={`walk-step${reached ? " done" : " dead"}`}>
                  <code>{char}</code>
                  <span className="walk-note">
                    {reached
                      ? `child ${characterToKey(char)}${
                          characterToKey(char) === 26 ? " (other)" : ""
                        }`
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
            Each node has 27 children: one per letter, plus one bucket for
            everything else. That folding is why the trie is case-insensitive,
            and why a wildcard is a bounded walk rather than a scan of every key.
          </p>
        </div>
      </div>
    </div>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="metric">
      <div className="metric-label">{label}</div>
      <div className="metric-value">{value}</div>
    </div>
  );
}
