/**
 * Cross-checks the browser's tokenizer, stemmer and phrase matcher against the
 * Python that defines them.
 *
 * `text-golden.json` is written by `scripts/generate_demo_data.py`, which
 * imports `trie_search` — so it records what the command line actually does
 * for a spread of documents and queries. The demo indexes text in the browser
 * rather than crawling, and this is what stops the two implementations from
 * drifting into disagreement about what a word is.
 */

import { describe, expect, it } from "vitest";

import golden from "../../data/demos/text-golden.json";
import { stem } from "./stem";
import {
  type BuiltIndex,
  buildFromDocuments,
  phraseMatches,
  quotedTerms,
  searchBuilt,
  tokenize,
} from "./trie";

const DOCUMENTS = golden.documents as Record<string, string>;

function build(stemming: boolean): BuiltIndex {
  return buildFromDocuments(DOCUMENTS, stemming);
}

describe("the tokenizer", () => {
  for (const [label, expected] of Object.entries(golden.tokenized)) {
    it(`splits ${label} the same way Python does`, () => {
      expect(tokenize(DOCUMENTS[label])).toEqual(expected);
    });
  }

  it("keeps internal punctuation and drops the surrounding kind", () => {
    expect(tokenize("well-known -- 'quoted' (bracketed).")).toEqual([
      "well-known", "quoted", "bracketed",
    ]);
  });

  it("drops tokens that are only punctuation", () => {
    expect(tokenize("-- --- ...")).toEqual([]);
  });
});

describe("the stemmer", () => {
  it("matches Python on every word in the fixture", () => {
    const wrong = Object.entries(golden.stems)
      .filter(([word, expected]) => stem(word) !== expected)
      .slice(0, 8);
    expect(wrong).toEqual([]);
  });

  it("has a fixture worth checking", () => {
    expect(Object.keys(golden.stems).length).toBeGreaterThan(30);
  });
});

describe("search, against the Python results", () => {
  for (const [i, testCase] of golden.cases.entries()) {
    const label = `${testCase.stemming ? "stemmed" : "plain"}: ${testCase.query}`;
    it(`${label} (case ${i})`, () => {
      const hits = searchBuilt(build(testCase.stemming), testCase.query);
      expect(hits.map((h) => h.url)).toEqual(testCase.hits.map((h) => h.url));
      hits.forEach((hit, j) => {
        expect(hit.matched).toEqual(testCase.hits[j].matched);
        expect(hit.score).toBeCloseTo(testCase.hits[j].score, 6);
      });
    });
  }
});

describe("phrases, independently of the fixture", () => {
  it("requires adjacency, where the bare query does not", () => {
    const index = build(false);
    const bare = searchBuilt(index, "park hours").map((h) => h.url);
    const phrase = searchBuilt(index, '"park hours"').map((h) => h.url);
    expect(bare).toContain("/apart");
    expect(phrase).not.toContain("/apart");
  });

  it("respects order", () => {
    const index = build(false);
    expect(searchBuilt(index, '"hours park"')).not.toHaveLength(0);
    expect(searchBuilt(index, '"hours park"').map((h) => h.url)).toContain("/reversed");
  });

  it("counts overlapping runs of a repeated word", () => {
    const index = buildFromDocuments({ "/x": "ha ha ha" }, false);
    expect(phraseMatches(index.positions, ["ha", "ha"], "/x")).toBe(2);
  });

  it("returns nothing when a word is absent", () => {
    expect(searchBuilt(build(false), '"park zebra"')).toEqual([]);
  });

  it("recognises a quoted query and only a quoted query", () => {
    expect(quotedTerms('"park hours"')).toEqual(["park", "hours"]);
    expect(quotedTerms("park hours")).toBeNull();
    expect(quotedTerms('""')).toEqual([]);
  });
});

describe("stemming in the browser index", () => {
  it("folds surface forms onto one key", () => {
    const index = build(true);
    const found = searchBuilt(index, "parks").map((h) => h.url);
    expect(found).toContain("/forms");
    expect(found).toContain("/adjacent");
  });

  it("records which surface forms produced each stem", () => {
    const index = build(true);
    expect(index.surfaces.park.sort()).toEqual(["park", "parked", "parking", "parks"]);
  });

  it("leaves wildcards unstemmed, because they are patterns", () => {
    const index = build(true);
    expect(searchBuilt(index, "par*").length).toBeGreaterThan(0);
  });

  it("positions still refer to the original word order", () => {
    const index = buildFromDocuments({ "/a": "parks parking parked" }, true);
    expect(index.positions.park["/a"]).toEqual([0, 1, 2]);
  });
});

describe("index construction", () => {
  it("counts tokens and page lengths", () => {
    const index = build(false);
    expect(index.tokens).toBe(
      Object.values(golden.tokenized).reduce((n, w) => n + w.length, 0),
    );
    for (const [label, words] of Object.entries(golden.tokenized)) {
      expect(index.corpus.lengths[label]).toBe(words.length);
    }
  });

  it("keeps counts and positions in step", () => {
    const index = build(false);
    for (const [term, byUrl] of Object.entries(index.postings)) {
      for (const [url, count] of Object.entries(byUrl)) {
        expect(index.positions[term][url]).toHaveLength(count);
      }
    }
  });

  it("handles an empty corpus without throwing", () => {
    const index = buildFromDocuments({}, false);
    expect(searchBuilt(index, "anything")).toEqual([]);
  });
});
