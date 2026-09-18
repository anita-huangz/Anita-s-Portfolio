"""Ranking metrics, the leave-one-out protocol, and what this dataset does.

The metrics are checked against hand-computed values, because a ranking metric
is easy to get subtly wrong and impossible to eyeball.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from rec_eval.data import (
    SchemaError,
    _parse_list,
    browsing_leak,
    load_catalogue,
    load_customers,
)
from rec_eval.evaluate import leave_one_out
from rec_eval.metrics import (
    average_precision,
    ndcg_at_k,
    precision_at_k,
    recall_at_k,
    reciprocal_rank,
    score_rankings,
)
from rec_eval.recommenders import (
    Context,
    browsing_oracle,
    category_share_of_similar_lists,
    different_category,
    expected_category_share,
    popularity,
    probability_column_correlations,
    random_ranking,
    same_category,
    similar_products,
)


@pytest.fixture(scope="module")
def catalogue():
    return load_catalogue()


@pytest.fixture(scope="module")
def customers():
    return load_customers()


@pytest.fixture(scope="module")
def evaluation(customers, catalogue):
    return leave_one_out(
        customers,
        catalogue,
        {
            "random": random_ranking(),
            "popularity": popularity(catalogue),
            "same category": same_category(catalogue),
            "different category": different_category(catalogue),
            "similar-product graph": similar_products(catalogue),
            "browsing (ORACLE)": browsing_oracle(catalogue),
        },
        k=5,
    )


# --------------------------------------------------------------------------- #
# Parsing
# --------------------------------------------------------------------------- #


def test_history_is_parsed_from_the_csvs_string_lists():
    assert _parse_list("['Books', 'Fashion']") == ["Books", "Fashion"]
    assert _parse_list("[]") == []
    assert _parse_list("") == []
    assert _parse_list(None) == []


def test_a_malformed_cell_does_not_crash_the_load():
    assert _parse_list("['unclosed") == []
    assert _parse_list("not a list") == []


def test_the_parser_cannot_execute_what_it_reads():
    """`ast.literal_eval`, not `eval`: these strings come from a file."""
    assert _parse_list("__import__('os').getcwd()") == []


def test_both_tables_load(catalogue, customers):
    assert len(catalogue) == 10_000
    assert len(customers) == 10_000
    assert len(catalogue.subcategories) == 24


def test_a_missing_column_is_caught(tmp_path):
    path = tmp_path / "bad.csv"
    pd.DataFrame({"Product_ID": ["P1"]}).to_csv(path, index=False)
    with pytest.raises(SchemaError, match="missing column"):
        load_catalogue(path)


def test_a_third_of_customers_cannot_be_evaluated(customers):
    """One purchase means nothing is left after holding it out.

    Excluded and counted, rather than the sample quietly shrinking.
    """
    assert len(customers.with_enough_history) == 6631
    assert len(customers) - len(customers.with_enough_history) == 3369


# --------------------------------------------------------------------------- #
# Metrics, against hand-computed values
# --------------------------------------------------------------------------- #


def test_recall_at_k():
    ranked = ["a", "b", "c", "d"]
    assert recall_at_k(ranked, {"a"}, 1) == 1.0
    assert recall_at_k(ranked, {"c"}, 2) == 0.0
    assert recall_at_k(ranked, {"a", "c"}, 4) == 1.0
    # Capped by k: two relevant items cannot both be found in a top-1 list.
    assert recall_at_k(ranked, {"a", "c"}, 1) == 1.0


def test_precision_at_k():
    ranked = ["a", "b", "c", "d"]
    assert precision_at_k(ranked, {"a", "b"}, 2) == 1.0
    assert precision_at_k(ranked, {"a"}, 4) == 0.25


def test_reciprocal_rank_is_one_over_the_first_hit():
    assert reciprocal_rank(["a", "b", "c"], {"a"}) == 1.0
    assert reciprocal_rank(["a", "b", "c"], {"c"}) == pytest.approx(1 / 3)
    assert reciprocal_rank(["a", "b"], {"z"}) == 0.0


def test_average_precision_rewards_early_hits():
    early = average_precision(["a", "x", "y", "z"], {"a", "y"}, 4)
    late = average_precision(["x", "y", "z", "a"], {"a", "y"}, 4)
    assert early > late
    # Hand-computed: hits at 1 and 3 -> (1/1 + 2/3) / 2
    assert early == pytest.approx((1 + 2 / 3) / 2)


def test_ndcg_is_one_for_a_perfect_ranking():
    assert ndcg_at_k(["a", "b", "c"], {"a"}, 3) == pytest.approx(1.0)
    assert ndcg_at_k(["a", "b", "c"], {"a", "b"}, 3) == pytest.approx(1.0)


def test_ndcg_discounts_logarithmically():
    """Moving 2nd to 1st matters more than moving 10th to 5th."""
    second = ndcg_at_k(["x", "a"], {"a"}, 2)
    assert second == pytest.approx(1 / np.log2(3) / (1 / np.log2(2)))
    assert 0 < second < 1


def test_a_miss_scores_zero_everywhere():
    ranked = ["a", "b"]
    assert recall_at_k(ranked, {"z"}, 2) == 0.0
    assert ndcg_at_k(ranked, {"z"}, 2) == 0.0
    assert average_precision(ranked, {"z"}, 2) == 0.0


def test_metrics_return_nan_with_no_relevant_items():
    assert np.isnan(recall_at_k(["a"], set(), 1))
    assert np.isnan(ndcg_at_k(["a"], set(), 1))


def test_scoring_needs_something_to_score():
    with pytest.raises(ValueError, match="no rankings"):
        score_rankings("x", [], k=5)


# --------------------------------------------------------------------------- #
# What this dataset is
# --------------------------------------------------------------------------- #


def test_browsing_history_contains_the_purchase_answer(customers, catalogue):
    """All 10,000 customers. Purchases were generated from browsing."""
    leak = browsing_leak(customers, catalogue)
    assert leak.rate == 1.0
    assert leak.is_deterministic


def test_every_customers_purchases_are_in_distinct_categories(customers, catalogue):
    """Which is what makes the obvious content-based rule backwards.

    Hold one purchase out and the rest are all in *other* categories, so
    "more of the same category" ranks the held-out item's category last.
    """
    category_of = catalogue.category_of
    for index in customers.with_enough_history:
        items = list(dict.fromkeys(customers.purchases[index]))
        categories = [category_of.get(i) for i in items]
        assert len(set(categories)) == len(categories)


def test_the_similar_product_lists_never_leave_the_category(catalogue):
    observed = category_share_of_similar_lists(catalogue)
    assert observed == pytest.approx(1.0)
    # Against about 17% if the lists were drawn at random.
    assert expected_category_share(catalogue) < 0.2


def test_the_recommendation_probability_column_is_noise(catalogue):
    """The notebook's regression target, correlated with nothing."""
    correlations = probability_column_correlations(catalogue)
    assert correlations.max() < 0.05


# --------------------------------------------------------------------------- #
# Recommenders and the protocol
# --------------------------------------------------------------------------- #


def test_every_recommender_returns_a_full_ranking(catalogue):
    context = Context(visible=["Jeans"], browsing=["Fashion"])
    for build in (random_ranking(), popularity(catalogue), same_category(catalogue),
                  different_category(catalogue), similar_products(catalogue),
                  browsing_oracle(catalogue)):
        ranked = build(context, catalogue)
        assert sorted(ranked) == catalogue.subcategories


def test_the_held_out_item_is_removed_from_the_visible_history(customers, catalogue):
    """A one-character mistake that makes every recommender look perfect."""
    evaluation = leave_one_out(
        customers, catalogue, {"same category": same_category(catalogue)}, k=5
    )
    # If the held-out item leaked into `visible`, same-category would score
    # near 1.0 rather than near zero.
    assert evaluation.named("same category").recall < 0.1


def test_the_obvious_content_rule_is_worse_than_random(evaluation):
    """13x worse, and by construction rather than by accident."""
    assert evaluation.named("same category").ndcg < evaluation.named("random").ndcg / 5


def test_its_inverse_beats_random(evaluation):
    """Because purchases sit in distinct categories, on this dataset only."""
    assert evaluation.named("different category").ndcg > evaluation.named("random").ndcg


def test_popularity_is_no_better_than_random_here(evaluation):
    """Items are near-uniform over 24 subcategories, so there is no head."""
    popular = evaluation.named("popularity").ndcg
    chance = evaluation.named("random").ndcg
    assert abs(popular - chance) < 0.02


def test_the_oracle_scores_perfectly_which_is_the_point(evaluation):
    """A recommender this good on this data is a bug report, not a result."""
    oracle = evaluation.named("browsing (ORACLE)")
    assert oracle.recall == pytest.approx(1.0)
    assert oracle.ndcg > 0.6
    assert oracle.ndcg > 4 * evaluation.named("random").ndcg


def test_the_similar_product_graph_inherits_the_category_problem(evaluation):
    """Its lists never leave the category, so it recommends the wrong one."""
    assert evaluation.named("similar-product graph").ndcg < evaluation.named("random").ndcg


def test_all_recommenders_face_the_same_held_out_items(customers, catalogue):
    """Paired comparison: otherwise a lucky draw looks like a difference."""
    first = leave_one_out(
        customers, catalogue,
        {"a": popularity(catalogue), "b": popularity(catalogue)}, k=5, seed=7,
    )
    assert first.named("a").ndcg == first.named("b").ndcg


def test_the_evaluation_reports_what_it_excluded(evaluation):
    assert evaluation.evaluated == 6631
    assert evaluation.excluded == 3369


def test_the_datasets_are_real_files_not_lfs_pointers():
    from rec_eval.data import CUSTOMERS, PRODUCTS

    for path in (CUSTOMERS, PRODUCTS):
        assert not path.read_text().splitlines()[0].startswith("version https://git-lfs")
