# Cybersecurity Threat Analysis

Six unsupervised methods, and the question that has to come first: **does this
dataset have any structure to find?**

It does not. Every column is an independent uniform draw, so the clusters, the
projections and the anomalies were all geometry.

```bash
python3 -m venv .venv && .venv/bin/pip install -e ".[dev]"
threat-structure                     # the whole analysis
threat-structure --section clusters  # or one part
pytest -q                            # 30 tests
```

---

## The test that should come before clustering

An unsupervised method has no ground truth to be wrong against. K-Means
returns k clusters whatever you hand it; a projection of independent noise
still looks like a cloud with edges; an outlier detector always flags 5% if you
ask for 5%. So all six methods in the original notebook produced pictures, and
none of them could say whether a picture meant anything.

Three tests, one per kind of structure:

```
Kolmogorov-Smirnov against a uniform on each column's own range:
  Incident Resolution Time (in Hours)    D=0.0160  p=0.418
  Number of Affected Users               D=0.0149  p=0.510
  Financial Loss (in Million $)          D=0.0117  p=0.804

chi-square against equal category frequencies:
  clears p<0.05: ['Attack Source'], and 0.35 were expected by chance

strongest association between any two categories: Target Industry x Attack Source, V=0.062
strongest correlation between any two numerics:   0.013
```

**All three numerics are flat.** Real financial-loss figures are heavy-tailed —
a few incidents cost far more than the rest. These are uniform on [0.5, 100],
which is what `np.random.uniform` produces.

**The categories are equally likely.** One of seven columns clears p < 0.05,
and testing seven columns produces 0.35 such results by chance. Reporting that
one as imbalance is the mistake the `consistent_with_chance` check exists to
prevent.

**No pair of columns relates to any other.** Max Cramér's V 0.062 across all 15
categorical pairs; max numeric correlation 0.013.

## The clusters, judged against a null

```
silhouette on the real data            0.0796
silhouette on independently shuffled   0.0810 +/- 0.0015
z = -0.90,  p = 0.810
-> better than noise: False
```

**The real data scores slightly *worse* than shuffled columns.**

The shuffle is the right null: it permutes each column independently, keeping
every marginal distribution exactly — same values, same counts — and destroying
only the relationships between columns. Sampling from a uniform box instead
would change the marginals too, confounding "no joint structure" with
"different spread".

| | |
|---|---|
| bootstrap stability (adjusted Rand index) | **0.484** [0.144, 0.919] |
| reproducible (0.75 is the usual bar) | no |

Real clusters survive a resample and the two runs agree. This partition is
redrawn each time, which means the boundaries are a property of the sample.

### The gap statistic, which can say "none"

| k | gap | s_k |
|---:|---:|---:|
| 1 | −0.2779 | 0.0068 |
| 2 | −0.3140 | 0.0061 |
| 3 | −0.3376 | 0.0037 |
| 4 | −0.3581 | 0.0026 |

**Chooses k = 1.** The gap *falls* monotonically with k, which is the signature
of uniform data: adding clusters never helps.

This is the only criterion here that can return that answer. Silhouette and
elbow plots are undefined at k = 1, so they are structurally incapable of
reporting "there are no clusters" however hard you squint at them — which is
why an elbow plot of noise still has an elbow.

## The outlier detectors, against each other

With no ground truth the detectors can't be graded — but they can be compared.

```
Isolation Forest flagged 150, LOF flagged 150, overlap 30
chance overlap would be 7.5
Jaccard 0.111,  overlap / chance = 4.00x
-> they agree: True
```

**And that is not validation**, which is the subtle part. Both methods rank
distance from the centre of the same cloud, so they agree on uniform noise too.
Agreement rules out one of them being broken; it says nothing about whether the
flagged rows are anomalous in any sense that matters.

The chance baseline is the part usually missing: two detectors each flagging 5%
of 3,000 rows overlap on 7.5 rows by coincidence, so the raw overlap of 30
looks like substantial agreement and the ratio is what to read.

```
where do the flagged rows sit in each column's distribution?
  percentile 0.490  Financial Loss (in Million $)          just a tail: False
  percentile 0.576  Number of Affected Users               just a tail: False
  percentile 0.342  Incident Resolution Time (in Hours)    just a tail: False
```

Not in any single column's tail, so the machinery is finding rare
*combinations* of categories in the 39-column one-hot space. On independent
uniform columns, rare combinations occur at random.

## A methodological floor I hit

A permutation p-value is `(hits + 1) / (draws + 1)`, so **with 10 draws the
smallest reachable p-value is 0.091** — the test cannot return a significant
result however large the effect. I found this when a test on synthetic data
with an obvious three-cluster structure (silhouette 0.807 against a null of
0.095) reported "not better than noise".

That is a property of the draw count, not of the data, and it reads exactly
like a null result. Both this package and the fake-news one now refuse fewer
than 19 draws and expose `smallest_possible_p`.

## Every test runs both ways

Each "no structure" result is paired with the same method on synthetic
incidents built with three genuine, well-separated groups:

| | real data | synthetic clusters |
|---|---|---|
| beats the shuffled null | no | yes, by 0.2 silhouette |
| bootstrap ARI | 0.484 | > 0.75 |
| gap statistic picks | k = 1 | k > 1 |
| uniformity test | all flat | rejects a lognormal column |
| association measure | V < 0.1 | V > 0.9 on a copied column |

## Layout

```
src/threat_structure/
  data.py        loading, encoding, the column-shuffle null       (pure)
  structure.py   KS, chi-square, Cramer's V, correlations         (pure)
  clustering.py  null comparison, bootstrap stability, gap        (pure)
  anomalies.py   detector agreement against chance, tail checks   (pure)
  cli.py         the report
tests/           30 tests, each paired against planted structure
notebooks/       the original, kept as the record (marked superseded)
```

## Limits

- **This is a statement about this file.** Real incident data has structure —
  ransomware clusters by sector and season, losses are heavy-tailed. Nothing
  here says the analysis was a bad idea, only that this dataset cannot support
  it.
- **t-SNE and DBSCAN are not re-run.** Both would produce pictures too, and the
  gap statistic already answers the question they were being asked.
- **The gap statistic's reference is a uniform box**, which is the standard
  construction but conservative for data with correlated columns. On this data
  that does not matter, since the columns are not correlated.

## Data

[Global Cybersecurity Threats 2015-2024](https://www.kaggle.com/datasets/atharvasoundankar/global-cybersecurity-threats-2015-2024)
— 3,000 incidents, 10 columns, bundled in [`data/`](data/). Synthetic, which
the dataset page does not say.
