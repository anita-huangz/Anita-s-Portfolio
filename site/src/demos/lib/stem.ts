/**
 * The Porter stemmer, ported from `systems/trie-search/src/trie_search/stem.py`.
 *
 * The demo indexes text you paste, in the browser, so the stemmer has to exist
 * here too — folding the query without folding the index, or the other way
 * round, would silently return nothing.
 *
 * `trie.test.ts` checks this against the same reference fixture the Python
 * suite uses, so the two cannot drift. Where the comments here are terse, the
 * Python is where the reasoning is written down.
 *
 * Reference: M.F. Porter, *An algorithm for suffix stripping*, Program 14(3),
 * 1980 — the paper, not his later revisions. See the Python module for which
 * rules that excludes and why it matters.
 */

const VOWELS = new Set("aeiou");

function isConsonant(word: string, index: number): boolean {
  const letter = word[index];
  if (VOWELS.has(letter)) return false;
  if (letter === "y") return index === 0 || !isConsonant(word, index - 1);
  return true;
}

/** Porter's *m*: how many vowel-consonant sequences the stem contains. */
export function measure(stem: string): number {
  let count = 0;
  let seenVowel = false;
  for (let i = 0; i < stem.length; i++) {
    if (isConsonant(stem, i)) {
      if (seenVowel) {
        count += 1;
        seenVowel = false;
      }
    } else {
      seenVowel = true;
    }
  }
  return count;
}

function hasVowel(stem: string): boolean {
  for (let i = 0; i < stem.length; i++) if (!isConsonant(stem, i)) return true;
  return false;
}

function endsDoubleConsonant(stem: string): boolean {
  return (
    stem.length >= 2 &&
    stem[stem.length - 1] === stem[stem.length - 2] &&
    isConsonant(stem, stem.length - 1)
  );
}

/** Porter's `*o`: consonant-vowel-consonant where the last is not w, x or y. */
export function cvc(stem: string): boolean {
  const n = stem.length;
  if (n < 3) return false;
  if (
    !(isConsonant(stem, n - 3) && !isConsonant(stem, n - 2) && isConsonant(stem, n - 1))
  ) {
    return false;
  }
  return !"wxy".includes(stem[n - 1]);
}

function replaceSuffix(
  word: string, suffix: string, replacement: string, minMeasure: number,
): string | null {
  if (!word.endsWith(suffix)) return null;
  const stem = word.slice(0, word.length - suffix.length);
  return measure(stem) > minMeasure ? stem + replacement : null;
}

const STEP2: [string, string][] = [
  ["ational", "ate"], ["tional", "tion"], ["enci", "ence"], ["anci", "ance"],
  ["izer", "ize"], ["abli", "able"], ["alli", "al"], ["entli", "ent"],
  ["eli", "e"], ["ousli", "ous"], ["ization", "ize"], ["ation", "ate"],
  ["ator", "ate"], ["alism", "al"], ["iveness", "ive"], ["fulness", "ful"],
  ["ousness", "ous"], ["aliti", "al"], ["iviti", "ive"], ["biliti", "ble"],
];

const STEP3: [string, string][] = [
  ["icate", "ic"], ["ative", ""], ["alize", "al"], ["iciti", "ic"],
  ["ical", "ic"], ["ful", ""], ["ness", ""],
];

const STEP4 = [
  "al", "ance", "ence", "er", "ic", "able", "ible", "ant", "ement",
  "ment", "ent", "ou", "ism", "ate", "iti", "ous", "ive", "ize",
];

/** Reduce a word to its Porter stem. */
export function stem(input: string): string {
  let word = input.toLowerCase();
  if (!word) return word;

  // Step 1a -- plurals.
  if (word.endsWith("sses")) word = word.slice(0, -2);
  else if (word.endsWith("ies")) word = word.slice(0, -2);
  else if (word.endsWith("ss")) { /* kept */ }
  else if (word.endsWith("s")) word = word.slice(0, -1);

  // Step 1b -- past tense and progressive.
  let secondOrThird = false;
  if (word.endsWith("eed")) {
    if (measure(word.slice(0, -3)) > 0) word = word.slice(0, -1);
  } else if (word.endsWith("ed") && hasVowel(word.slice(0, -2))) {
    word = word.slice(0, -2);
    secondOrThird = true;
  } else if (word.endsWith("ing") && hasVowel(word.slice(0, -3))) {
    word = word.slice(0, -3);
    secondOrThird = true;
  }

  if (secondOrThird) {
    if (word.endsWith("at") || word.endsWith("bl") || word.endsWith("iz")) {
      word += "e";
    } else if (endsDoubleConsonant(word) && !"lsz".includes(word[word.length - 1])) {
      word = word.slice(0, -1);
    } else if (measure(word) === 1 && cvc(word)) {
      word += "e";
    }
  }

  // Step 1c -- terminal y to i.
  if (word.endsWith("y") && hasVowel(word.slice(0, -1))) {
    word = word.slice(0, -1) + "i";
  }

  // Steps 2 and 3 -- derivational suffixes, longest match first.
  for (const table of [STEP2, STEP3]) {
    for (const [suffix, replacement] of table) {
      const swapped = replaceSuffix(word, suffix, replacement, 0);
      if (swapped !== null) {
        word = swapped;
        break;
      }
    }
  }

  // Step 4 -- strip entirely, from a long stem only.
  let stripped = false;
  for (const suffix of STEP4) {
    if (word.endsWith(suffix)) {
      const rest = word.slice(0, word.length - suffix.length);
      if (measure(rest) > 1) word = rest;
      stripped = true;
      break;
    }
  }
  if (!stripped && word.endsWith("ion")) {
    const rest = word.slice(0, -3);
    if (measure(rest) > 1 && (rest.endsWith("s") || rest.endsWith("t"))) word = rest;
  }

  // Step 5a -- a trailing e.
  if (word.endsWith("e")) {
    const m = measure(word.slice(0, -1));
    if (m > 1 || (m === 1 && !cvc(word.slice(0, -1)))) word = word.slice(0, -1);
  }

  // Step 5b -- a doubled l.
  if (measure(word) > 1 && endsDoubleConsonant(word) && word.endsWith("l")) {
    word = word.slice(0, -1);
  }

  return word;
}
