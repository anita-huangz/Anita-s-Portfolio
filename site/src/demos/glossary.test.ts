/**
 * Guards the glossary against the two ways it can rot silently.
 *
 * A mistyped `<Term id="sharp">` renders as plain text with no explanation and
 * looks exactly like a term nobody thought to define, so the id has to be
 * checked against the glossary mechanically. And an alias pointing at two
 * different entries means one of them is unreachable, which no amount of
 * clicking around would reveal.
 */

import { describe, expect, it } from "vitest";

import { GLOSSARY, GLOSSARY_IDS, lookupTerm } from "./glossary";

// Vite's own glob rather than `node:fs`, so the test needs no `@types/node`
// and still typechecks under `tsc -b`, which the build runs.
const SOURCES = import.meta.glob("../**/*.tsx", {
  query: "?raw",
  import: "default",
  eager: true,
}) as Record<string, string>;

/**
 * Every `<Term id="x">`, every `term="x"` prop, and every id reached through a
 * lookup table across the app.
 *
 * The third case exists because a table whose rows each carry a different term
 * cannot write the id inline — it maps a row key to an id, as `METHOD_TERM` and
 * `RULE_TERM` do. Those ids are just as real as the inline ones and rot just as
 * silently, so any `const *_TERM: Record<string, string>` is scanned too. The
 * convention is the suffix: name a lookup table `SOMETHING_TERM` and the test
 * will check it.
 */
function usedTermIds(): { id: string; file: string }[] {
  const out: { id: string; file: string }[] = [];
  for (const [file, text] of Object.entries(SOURCES)) {
    for (const m of text.matchAll(/<Term\s+id="([^"]+)"/g)) {
      out.push({ id: m[1], file });
    }
    for (const m of text.matchAll(/\bterm="([^"]+)"/g)) {
      out.push({ id: m[1], file });
    }
    for (const table of text.matchAll(
      /const\s+\w*_TERM\s*:\s*Record<string,\s*string>\s*=\s*\{([^}]*)\}/g,
    )) {
      for (const m of table[1].matchAll(/:\s*"([^"]+)"/g)) {
        out.push({ id: m[1], file });
      }
    }
  }
  return out;
}

describe("the glossary", () => {
  it("defines every term the demos reference", () => {
    const missing = usedTermIds()
      .filter(({ id }) => !lookupTerm(id))
      .map(({ id, file }) => `${id} (${file})`);
    expect(missing).toEqual([]);
  });

  it("is actually referenced — the demos use terms", () => {
    // Guards against a refactor quietly dropping every <Term> from the UI.
    expect(usedTermIds().length).toBeGreaterThan(30);
  });

  it("resolves ids, display terms, and aliases alike", () => {
    expect(lookupTerm("sharpe")?.term).toBe("Sharpe ratio");
    expect(lookupTerm("Sharpe ratio")?.term).toBe("Sharpe ratio");
    expect(lookupTerm("sharpe ratio")?.term).toBe("Sharpe ratio");
    // Case and surrounding space must not matter: labels come from the UI.
    expect(lookupTerm("  ANNUALIZED  ")?.term).toBe("Annualised return");
    expect(lookupTerm("not a term")).toBeUndefined();
  });

  it("gives every entry a term and a real definition", () => {
    for (const [id, entry] of Object.entries(GLOSSARY)) {
      expect(entry.term.length, id).toBeGreaterThan(1);
      // Long enough to explain something, short enough to read in a popover.
      expect(entry.body.length, id).toBeGreaterThan(80);
      expect(entry.body.length, id).toBeLessThan(600);
      expect(entry.body.trim().endsWith("."), id).toBe(true);
      if (entry.here) expect(entry.here.length, id).toBeGreaterThan(20);
    }
  });

  it("never points one alias at two entries", () => {
    const seen = new Map<string, string>();
    for (const [id, entry] of Object.entries(GLOSSARY)) {
      for (const key of [id, entry.term, ...(entry.aliases ?? [])]) {
        const lower = key.toLowerCase();
        const prior = seen.get(lower);
        expect(prior ?? id, `"${key}" claimed by both ${prior} and ${id}`).toBe(id);
        seen.set(lower, id);
      }
    }
  });

  it("has no unused entries", () => {
    // An entry nothing links to is dead weight, and usually means a label was
    // renamed without its term following.
    const used = new Set(
      usedTermIds()
        .map(({ id }) => lookupTerm(id))
        .filter(Boolean)
        .map((entry) => entry!.term),
    );
    const orphans = GLOSSARY_IDS.filter((id) => !used.has(GLOSSARY[id].term));
    expect(orphans).toEqual([]);
  });
});
