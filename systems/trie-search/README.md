# Trie Search

Crawl a website, index every word into a trie, and search it by prefix or with
a single-character wildcard.

```
$ trie-search https://scrapple.fly.dev/parks --depth 2 --query "par?"
Crawled 34 page(s), 8,112 words.
Indexed 1,204 distinct words.

                    Results for 'par?'
┏━━━━━━━┳━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓
┃  Word ┃ Pages ┃ URL(s)                                  ┃
┡━━━━━━━╇━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┩
│  park │    31 │ https://scrapple.fly.dev/parks          │
│  part │     4 │ https://scrapple.fly.dev/parks/12       │
└───────┴───────┴─────────────────────────────────────────┘
```

Without `--query` it drops into an interactive prompt.

## Run it

```bash
python3 -m venv .venv && .venv/bin/pip install -e ".[dev]"
trie-search https://example.com --depth 1
trie-bench      # the trie against a dictionary scan
pytest -q       # 84 tests, no network
ruff check .
```

## Layout

```
src/trie_search/
  trie.py      the trie: MutableMapping + prefix and wildcard search
  fetch.py     HTTP, HTML extraction, tokenizing
  crawler.py   breadth-first crawl, index building
  cli.py       argument parsing, rich tables, interactive prompt
```

## How the trie works

Each node has up to 27 children: one per letter `a-z`, plus one bucket for
everything else. Keys fold into that alphabet, which makes the trie
**case-insensitive** and means `don't` and `don_t` are the same key.

That's lossy, and it's the trade: a fixed small alphabet is what keeps wildcard
search a simple bounded walk instead of a scan. `original_keys()` gives back
the text as it was inserted when you need it.

## Is the trie worth it? Measured, not assumed

A trie is more code than a dictionary, and it is lossy — the fixed alphabet
above folds case and punctuation away. That trade only pays if prefix and
wildcard lookup are genuinely cheaper than scanning the keys, so the project
measures it rather than asserting it:

```
$ trie-bench
Prefix 'ab' and wildcard '?ar?', best of 5. Milliseconds.

                      PREFIX                       WILDCARD
    words      trie     scan     hits      trie     scan     hits
------------------------------------------------------------------------
    5,000     0.008    0.056       12     0.013    0.284        0
   25,000     0.026    0.265       41     0.020    1.388        5
  100,000     0.095    1.096      141     0.031    5.825       22

Over a 20x larger vocabulary the scan got 20x slower and the trie 12x.
```

The ratio is not the interesting number — it moves around with how many words
happen to match. The shape of the columns is. **The scan grows with the
vocabulary** because it visits every key: 20× the words, 20× the time, dead
linear. **The trie grows with the answer** — its 12× tracks the hit count
going from 12 to 141, not the vocabulary going from 5,000 to 100,000.

That is the whole case for the data structure, and it is why the wildcard
column is the more lopsided of the two: a regex scan still touches all 100,000
keys to return 22 of them, while the trie's `?` is a bounded branch over 27
children at one depth.

`tests/test_benchmark.py` asserts the trie and the scan return **the same
words** for every prefix and pattern it tries. A faster answer that disagreed
with the obvious one would not be an optimisation.

## Bugs this version fixes

**`__iter__` yielded `(key, value)` pairs instead of keys.**

`MutableMapping` builds `keys()`, `values()`, and `items()` on top of
`__iter__` by doing `self[element]` for each element yielded. Yielding a tuple
made every one of those raise `KeyError`, and `dict(trie)` didn't work either.
The class claimed to be a mapping and failed the mapping contract.

**Wildcard search matched `*` while everything documented `?`.**

The docstring said `c?t would match 'cat', 'cut', 'cot'`; the implementation
checked `if char == '*'`. Every documented example returned nothing.

**The visited-URL set was a module-level global.**

```python
_seen_already = set()      # module scope
```

So the *second* crawl in a process raised "already seen this run" on every URL
and returned nothing. It also made the crawler untestable, since state leaked
between tests. The visited set now belongs to the crawl.

**Script and style bodies were indexed as words.** `text_content()` includes
them, so a page's JavaScript became searchable text.

**Adjacent elements were glued together.** `text_content()` concatenates with
no separator, so `<a>C</a><p>alpha page</p>` produced `Calpha page` — "C" and
"alpha" both became unfindable. Text nodes are now joined with a space.

**Fetch failures were silently swallowed** by a bare `except: continue`, so a
crawl where every page 500'd was indistinguishable from a site with no content.
Failures are now collected in `CrawlResult.failures` and reported.

Also: URL fragments are stripped before dedup (`/page` and `/page#section` are
one document), off-site links are not followed, and `max_pages` caps a runaway
crawl.

## Notes

- Crawling is restricted to an allowlist of URL prefixes, defaulting to the
  start URL. It's a guardrail against wandering off a test site, not a security
  boundary.
- `robots.txt` is not consulted and there is no rate limiting. Point this at
  test sites.
- The index maps word → set of URLs. It has no ranking, no phrase search, and
  no stemming — "park" and "parks" are separate keys.
