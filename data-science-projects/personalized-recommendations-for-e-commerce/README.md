# E-commerce Recommendations

A content-based recommender with **ranking metrics**, a leave-one-out protocol,
and the baselines that are supposed to be easy to beat.

The headline is about the dataset: every customer's purchases sit in *distinct*
categories by construction, which makes the obvious content-based rule —
recommend more of what they already buy — **14× worse than random**.

```bash
python3 -m venv .venv && .venv/bin/pip install -e ".[dev]"
rec-eval                     # the whole evaluation
rec-eval --section data      # or one part
pytest -q                    # 28 tests
```

---

## What the data actually supports

**There is no user-item interaction matrix.** Customers carry a
`Purchase_History` of subcategory *names* — `['Biography', 'Jeans']` — and
products carry IDs that appear nowhere in the customer table. Collaborative
filtering is not merely hard here, it is undefined: there is no "users who
bought this also bought", because no purchase is attached to a product.

What exists is a 24-subcategory taxonomy shared by both tables, which supports
content-based recommendation and can be evaluated properly. The original
notebook instead trained classifiers to predict `Probability_of_Recommendation`
— a column that correlates with nothing else in the table (max |r| = 0.017) and
is uniform on [0.1, 1.0]. That is a regression on noise, and it is not
recommendation.

## Ranking metrics, because a recommender produces a list

Accuracy and AUC ask "was this item right". A recommender is judged on *where*
the right item landed — 2nd is nearly as good as 1st, 400th is useless — and no
classification metric knows the difference.

```
6,631 customers evaluated, 3,369 excluded for having a single purchase

recommender             recall@5     prec@5     MAP@5     MRR   NDCG@5
random                    0.2083     0.0417    0.0959  0.1582   0.1234
popularity                0.2000     0.0400    0.0916  0.1541   0.1182
same category             0.0232     0.0046    0.0046  0.0746   0.0090
different category        0.2734     0.0547    0.1244  0.1918   0.1609
similar-product graph     0.0446     0.0089    0.0101  0.0822   0.0183
browsing (ORACLE)         1.0000     0.2000    0.5164  0.5164   0.6369
```

A third of customers cannot be evaluated at all: hold out the only purchase of
a one-purchase customer and there is no history left to rank from. They are
excluded and **counted**, rather than the sample quietly shrinking.

## Three findings

### The obvious rule is exactly backwards

Every customer's purchases are in **distinct categories** — all 6,631 of the
evaluable ones. Browsing `['Books', 'Fashion']` produces exactly one purchase
from Books and one from Fashion.

So when you hold one purchase out, the remaining history is entirely in *other*
categories, and "recommend more of the same category" ranks the held-out item's
category **last**. NDCG 0.0090 against random's 0.1234.

Its inverse — recommend from categories the customer has *not* bought from —
beats random (0.1609). That is true on this dataset and no other, and it is a
statement about the generator, not a recommendation strategy.

The `Similar_Product_List` graph inherits the same problem: 100% of its entries
are in the listing product's category, against 17% by chance, so it recommends
confidently into the wrong category.

### Popularity ties with random

The baseline that beats a great many published recommenders does nothing here,
because the 24 subcategories are near-uniform — there is no popular head to
exploit. Worth reporting: "we beat popularity" means nothing on a flat
catalogue.

### Browsing history is the answer

```
browsing covers a purchased category for 10,000/10,000 customers = 1.0000
```

The browsing set is *exactly* the set of categories purchased from. So a
recommender given browsing history reaches **recall@5 = 1.0000** — it is not a
model, it is the answer arriving through a different column.

It is included on purpose, scoring four times everything else, because that is
what leakage looks like from the outside. A result this good on this data is a
bug report.

To keep that honest, a recommender receives a `Context` with `visible` and
`browsing` as separate fields, so reading the leaky column is a visible choice
rather than an accident of what happened to be in scope.

## The protocol

For each customer: hide one purchased subcategory, rank all 24 from what
remains, record where the hidden one landed. Two details decide whether the
number means anything:

- **The held-out item must leave the visible history.** Leaving it in makes
  every recommender look perfect, and it is a one-character mistake. There is a
  test for it.
- **Every recommender faces the same held-out items**, so the comparison is
  paired — otherwise a lucky draw is indistinguishable from a real difference.

## Layout

```
src/rec_eval/
  data.py          parsing, the taxonomy, the browsing-leak check   (pure)
  metrics.py       recall@k, precision@k, MAP, MRR, NDCG            (pure)
  recommenders.py  random, popularity, content rules, the oracle    (pure)
  evaluate.py      leave-one-out, paired across recommenders        (pure)
  cli.py           the report
tests/             28 tests; metrics checked against hand-computed values
notebooks/         the original, kept as the record
```

## Limits

- **No collaborative filtering, because the data cannot support it.** With a
  real interaction log, matrix factorisation or item-item CF would be the
  first thing to try and would likely beat all of this.
- **24 items is a tiny catalogue.** recall@5 out of 24 is a fifth of the
  catalogue, so the cut-off flatters every method; the ranking between methods
  is what to read, not the level.
- **No temporal split.** There are no timestamps, so "the next purchase" is a
  random held-out item rather than a later one — which is the weaker protocol.
- **No cold-start handling**, because every customer here has history.

## Data

[Personalized Recommendations for E-Commerce](https://www.kaggle.com/datasets/suvroo/personalized-recommendations-for-e-commerce)
— 10,000 customers and 10,000 products, bundled in [`data/`](data/). Synthetic,
with a generator that is visible in the results.
