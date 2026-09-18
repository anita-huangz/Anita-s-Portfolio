"""Recommenders, and the baselines that are supposed to be easy to beat.

The popularity baseline is here because it is the result that keeps being
rediscovered: recommending the most common items to everybody, with no
personalisation at all, beats a great many published recommenders. Any
personalised model that cannot clear it has not earned its complexity.

Each recommender takes the *visible* history -- what is left after holding one
purchase out -- and returns every subcategory in ranked order. Returning the
full ranking rather than a top-k lets the metrics choose their own cut-off,
and makes reciprocal rank computable.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from .data import Catalogue


@dataclass(frozen=True)
class Context:
    """What a recommender is allowed to see about one customer.

    `visible` is the purchase history with the held-out item removed.
    `browsing` is separate and deliberately so: on this dataset it *contains
    the answer*, so a recommender that reads it is leaking, and the seam makes
    that a visible choice rather than an accident of which column was in
    scope.
    """

    visible: list[str]
    browsing: list[str] = field(default_factory=list)


Recommender = Callable[[Context, Catalogue], list[str]]


def random_ranking(seed: int = 0) -> Recommender:
    """The floor. Anything below this is broken rather than weak."""
    rng = np.random.default_rng(seed)

    def recommend(context: Context, catalogue: Catalogue) -> list[str]:
        return list(rng.permutation(catalogue.subcategories))

    return recommend


def popularity(catalogue: Catalogue) -> Recommender:
    """Most common subcategories first, identical for every customer.

    Precomputed once, deliberately: a popularity model has no per-customer
    state, and pretending otherwise would hide how strong an unpersonalised
    baseline is.
    """
    order = list(catalogue.popularity().index)

    def recommend(context: Context, _: Catalogue) -> list[str]:
        return order

    return recommend


def same_category(catalogue: Catalogue) -> Recommender:
    """Content-based: rank items from the categories the customer already buys.

    The simplest genuinely personalised rule the data supports. Ties inside a
    category break by popularity, so it degrades to the popularity baseline
    for a customer with no usable history rather than to a random order.
    """
    category_of = catalogue.category_of
    popular = list(catalogue.popularity().index)

    def recommend(context: Context, _: Catalogue) -> list[str]:
        wanted = {category_of.get(item) for item in context.visible}
        inside = [i for i in popular if category_of.get(i) in wanted]
        outside = [i for i in popular if category_of.get(i) not in wanted]
        return inside + outside

    return recommend


def similar_products(catalogue: Catalogue) -> Recommender:
    """Use the catalogue's own `Similar_Product_List` as a co-occurrence graph.

    Worth trying because the column exists and is not random -- every listed
    item is in the same category as the product listing it, against 17% by
    chance. Whether that is *more* useful than knowing the category is exactly
    the question, since it may carry no information the category does not.
    """
    counts: dict[str, dict[str, int]] = {}
    for row in catalogue.frame.itertuples():
        source = row.Subcategory
        neighbours = counts.setdefault(source, {})
        for item in row.similar:
            if item != source:
                neighbours[item] = neighbours.get(item, 0) + 1

    popular = list(catalogue.popularity().index)

    def recommend(context: Context, _: Catalogue) -> list[str]:
        scores: dict[str, float] = {}
        for item in context.visible:
            for neighbour, weight in counts.get(item, {}).items():
                scores[neighbour] = scores.get(neighbour, 0.0) + weight
        ranked = sorted(scores, key=lambda i: (-scores[i], popular.index(i)))
        remaining = [i for i in popular if i not in scores]
        return ranked + remaining

    return recommend


def browsing_oracle(catalogue: Catalogue) -> Recommender:
    """Ranks by the customer's browsing categories. Included to expose a leak.

    On this dataset the browsing set is *exactly* the set of categories the
    customer purchased from -- all 10,000 of them, with one purchase per
    browsed category. So browsing names the held-out item's category directly,
    and this is not a model at all; it is the answer arriving through a
    different column.

    It is here to be seen scoring far above everything else, because that is
    what leakage looks like from the outside. A recommender this good on this
    data would be a bug report.
    """
    category_of = catalogue.category_of
    popular = list(catalogue.popularity().index)

    def recommend(context: Context, _: Catalogue) -> list[str]:
        # The categories the customer purchased from, minus the ones still
        # visible -- which leaves the held-out item's category.
        seen = {category_of.get(item) for item in context.visible}
        target = [c for c in context.browsing if c not in seen] or context.browsing
        wanted = set(target)
        inside = [i for i in popular if category_of.get(i) in wanted]
        outside = [i for i in popular if category_of.get(i) not in wanted]
        return inside + outside

    return recommend


def different_category(catalogue: Catalogue) -> Recommender:
    """Rank items from categories the customer has *not* bought from.

    Included because the obvious content-based rule is exactly backwards here.
    Every customer's purchases sit in distinct categories by construction, so
    the held-out item is never in a category the visible history covers --
    which makes "more of the same" the worst possible ordering and its
    complement a genuinely strong one, on this dataset and no other.
    """
    category_of = catalogue.category_of
    popular = list(catalogue.popularity().index)

    def recommend(context: Context, _: Catalogue) -> list[str]:
        seen = {category_of.get(item) for item in context.visible}
        outside = [i for i in popular if category_of.get(i) not in seen]
        inside = [i for i in popular if category_of.get(i) in seen]
        return outside + inside

    return recommend


def category_share_of_similar_lists(catalogue: Catalogue) -> float:
    """Share of `Similar_Product_List` entries in the listing product's category.

    1.0 means the column is category-constrained by construction. Compare with
    `expected_category_share` to see whether that is more than chance.
    """
    category_of = catalogue.category_of
    inside, total = 0, 0
    for row in catalogue.frame.itertuples():
        for item in row.similar:
            total += 1
            inside += int(category_of.get(item) == row.Category)
    return inside / total if total else float("nan")


def expected_category_share(catalogue: Catalogue) -> float:
    """What the share would be if the lists were drawn at random."""
    shares = catalogue.frame["Category"].value_counts(normalize=True)
    return float((shares**2).sum())


def probability_column_correlations(catalogue: Catalogue) -> pd.Series:
    """Does `Probability_of_Recommendation` relate to anything?

    The notebook's regression target. If it correlates with nothing in the
    table, a model predicting it is fitting noise -- and reporting an R-squared
    for that is reporting how much noise a flexible model can absorb.
    """
    frame = catalogue.frame
    if "Probability_of_Recommendation" not in frame:
        return pd.Series(dtype=float)
    numeric = frame.select_dtypes("number").drop(
        columns=["Probability_of_Recommendation"], errors="ignore"
    )
    target = frame["Probability_of_Recommendation"]
    return numeric.apply(target.corr).abs().sort_values(ascending=False)
