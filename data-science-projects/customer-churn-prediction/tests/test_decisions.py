"""Data repair, calibration, and the decision layer."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from churn.calibration import (
    brier_score,
    brier_skill_score,
    expected_calibration_error,
    reliability_curve,
)
from churn.data import (
    REDUNDANT_LEVELS,
    SchemaError,
    collapse_redundant_levels,
    collinearity_with_duration,
    cox_design_matrix,
    load,
    repair_total_charges,
)
from churn.economics import (
    Campaign,
    best_threshold,
    customer_value,
    expected_months_remaining,
    expected_value_curve,
    targeting_comparison,
)


@pytest.fixture(scope="module")
def data():
    return load()


# --------------------------------------------------------------------------- #
# Data repair
# --------------------------------------------------------------------------- #


def test_the_unbilled_customers_get_zero_not_the_column_mean(data):
    """Eleven rows have a blank TotalCharges. All eleven have tenure 0.

    The notebook filled them with the column mean, 2283.30, which tells the
    model that eleven brand-new customers have already paid two thousand
    dollars. The right answer is derivable, not a guess.
    """
    new_customers = data.frame[data.frame.tenure == 0]
    assert len(new_customers) == 11
    assert (new_customers.TotalCharges == 0).all()


def test_a_blank_charge_on_an_established_customer_is_an_error():
    """Zero is right for an unbilled customer and wrong for missing data."""
    frame = pd.DataFrame({"TotalCharges": ["", "100"], "tenure": [24, 3]})
    with pytest.raises(SchemaError, match="non-zero tenure"):
        repair_total_charges(frame)


def test_repairing_a_clean_column_changes_nothing():
    frame = pd.DataFrame({"TotalCharges": ["10.5", "20"], "tenure": [1, 2]})
    assert repair_total_charges(frame).tolist() == [10.5, 20.0]


def test_the_dataset_is_mostly_censored(data):
    """Which is why a classifier is the wrong tool for the timing question."""
    assert data.censoring_rate == pytest.approx(0.7346, abs=1e-4)
    assert data.churn_rate == pytest.approx(0.2654, abs=1e-4)


def test_redundant_levels_are_collapsed(data):
    """"No internet service" is the same 1,526 customers as InternetService=No."""
    for column in ["OnlineSecurity", "TechSupport", "StreamingTV"]:
        assert "No internet service" not in set(data.frame[column])
    assert "No phone service" not in set(data.frame.MultipleLines)


def test_collapsing_is_lossless(data):
    """The information survives in the column that already carried it."""
    no_internet = data.frame.InternetService == "No"
    assert no_internet.sum() == 1526
    # Every one of them still reads "No" for every add-on.
    assert (data.frame.loc[no_internet, "OnlineSecurity"] == "No").all()


def test_collapsing_leaves_numeric_columns_alone():
    frame = pd.DataFrame({"gender": ["Male"], "tenure": [5], "MonthlyCharges": [10.0]})
    out = collapse_redundant_levels(frame)
    assert out.tenure.tolist() == [5]
    assert out.MonthlyCharges.tolist() == [10.0]


def test_the_design_matrix_is_full_rank(data):
    """Before collapsing it was 27 columns of rank 21, and Cox could not fit."""
    X = cox_design_matrix(data)
    assert np.linalg.matrix_rank(X.to_numpy(float)) == X.shape[1]


def test_the_duration_is_kept_out_of_its_own_design_matrix(data):
    """`tenure` is the time axis; `TotalCharges` is it in disguise."""
    assert abs(collinearity_with_duration(data)["TotalCharges"]) > 0.8
    X = cox_design_matrix(data)
    assert "tenure" not in X.columns
    assert "TotalCharges" not in X.columns


def test_a_missing_column_is_caught_at_load(tmp_path):
    path = tmp_path / "bad.csv"
    pd.DataFrame({"customerID": ["1"], "Churn": ["No"]}).to_csv(path, index=False)
    with pytest.raises(SchemaError, match="missing column"):
        load(path)


def test_redundant_levels_are_declared_not_hardcoded():
    assert REDUNDANT_LEVELS["No internet service"] == "No"


# --------------------------------------------------------------------------- #
# Calibration
# --------------------------------------------------------------------------- #


def test_a_perfect_forecast_scores_zero_brier():
    label = np.array([1, 0, 1, 0])
    assert brier_score(label.astype(float), label) == 0.0


def test_brier_skill_is_zero_for_the_base_rate():
    """Predicting the overall rate for everyone is the thing to beat."""
    label = np.array([1, 0, 0, 0, 1, 0, 0, 0])
    constant = np.full(len(label), label.mean())
    assert brier_skill_score(constant, label) == pytest.approx(0.0)


def test_brier_skill_is_negative_for_a_worse_than_useless_model():
    label = np.array([1, 1, 0, 0])
    backwards = np.array([0.1, 0.1, 0.9, 0.9])
    assert brier_skill_score(backwards, label) < 0


def test_a_calibrated_forecast_has_near_zero_error():
    rng = np.random.default_rng(0)
    p = rng.uniform(0, 1, 40_000)
    label = (rng.uniform(0, 1, 40_000) < p).astype(int)
    assert expected_calibration_error(p, label) < 0.01


def test_a_systematically_overconfident_forecast_is_caught():
    rng = np.random.default_rng(1)
    p = rng.uniform(0, 1, 20_000)
    label = (rng.uniform(0, 1, 20_000) < p / 2).astype(int)  # half as likely as claimed
    assert expected_calibration_error(p, label) > 0.15


def test_ranking_and_calibration_are_different_properties():
    """Squaring every probability leaves AUC untouched and ruins calibration.

    This is why AUC alone cannot license multiplying a score by a dollar
    amount, which is exactly what the expected-value threshold does.
    """
    from sklearn.metrics import roc_auc_score

    rng = np.random.default_rng(2)
    p = rng.uniform(0, 1, 20_000)
    label = (rng.uniform(0, 1, 20_000) < p).astype(int)
    squashed = p**2
    assert roc_auc_score(label, squashed) == pytest.approx(roc_auc_score(label, p))
    assert expected_calibration_error(squashed, label) > 10 * expected_calibration_error(p, label)


def test_empty_bins_stay_empty():
    """A model that never predicts above 0.5 should look like one."""
    curve = reliability_curve(np.array([0.1, 0.2, 0.3]), np.array([0, 0, 1]), bins=10)
    assert curve.count[-1] == 0
    assert np.isnan(curve.predicted[-1])


# --------------------------------------------------------------------------- #
# Economics
# --------------------------------------------------------------------------- #


def test_a_campaign_rejects_impossible_assumptions():
    with pytest.raises(ValueError, match="probability"):
        Campaign(acceptance=1.5)
    with pytest.raises(ValueError, match="negative"):
        Campaign(offer_cost=-1)


def test_customer_value_is_capped_at_the_horizon():
    campaign = Campaign(horizon_months=12, margin=0.5)
    value = customer_value(np.array([100.0]), np.array([99.0]), campaign)
    assert value[0] == pytest.approx(100 * 12 * 0.5)


def test_expected_months_is_the_area_under_the_curve():
    # A customer certain to stay for the whole horizon.
    times = np.array([1.0, 2.0, 3.0])
    survival = np.ones((1, 3))
    assert expected_months_remaining(survival, times, 3.0)[0] == pytest.approx(3.0)
    # One who leaves immediately.
    assert expected_months_remaining(np.zeros((1, 3)), times, 3.0)[0] == pytest.approx(1.0)


def test_the_best_threshold_beats_targeting_everybody():
    rng = np.random.default_rng(4)
    n = 4000
    churned = rng.random(n) < 0.27
    p = np.clip(churned * 0.5 + rng.normal(0.25, 0.15, n), 0.01, 0.99)
    value = np.full(n, 400.0)
    campaign = Campaign(offer_cost=30, acceptance=0.3)
    curve = expected_value_curve(p, churned, value, campaign)
    best = best_threshold(curve)
    target_all = curve[0]
    assert best.expected_value >= target_all.expected_value


def test_the_optimal_threshold_is_not_one_half():
    """The two errors do not cost the same, so 0.5 has no claim on being right."""
    rng = np.random.default_rng(5)
    n = 4000
    churned = rng.random(n) < 0.27
    p = np.clip(churned * 0.45 + rng.normal(0.25, 0.15, n), 0.01, 0.99)
    value = np.full(n, 600.0)
    curve = expected_value_curve(p, churned, value, Campaign(offer_cost=25))
    assert abs(best_threshold(curve).threshold - 0.5) > 0.05


def test_a_prohibitive_offer_means_calling_nobody():
    rng = np.random.default_rng(6)
    n = 1000
    churned = rng.random(n) < 0.27
    p = rng.random(n)
    value = np.full(n, 10.0)
    curve = expected_value_curve(p, churned, value, Campaign(offer_cost=10_000))
    # Every campaign loses money here, so the right answer is not to run one.
    best = best_threshold(curve)
    assert best.targets_nobody
    assert best.expected_value == 0.0


def test_ties_break_toward_calling_fewer_people():
    results = expected_value_curve(
        np.array([0.9, 0.9]),
        np.array([True, True]),
        np.array([100.0, 100.0]),
        Campaign(offer_cost=0, acceptance=1.0),
        thresholds=np.array([0.1, 0.5]),
    )
    assert best_threshold(results).threshold == 0.5


def test_ranking_by_value_beats_ranking_by_probability(data):
    """The survival model's payoff, on a fixed budget.

    A classifier says who is likely to leave. It cannot say what they were
    worth, because "will churn" is the same label for a customer with eight
    months left and one with four years. Ranking by probability times value
    spends the same budget better.
    """
    rng = np.random.default_rng(7)
    n = 5000
    churned = rng.random(n) < 0.27
    p = np.clip(churned * 0.4 + rng.normal(0.25, 0.15, n), 0.01, 0.99)
    # Value varies a lot and is only weakly related to churn risk, which is
    # what makes the two rankings disagree.
    value = rng.lognormal(6.0, 0.8, n)
    result = targeting_comparison(p, churned, value, Campaign(), budget=800)
    assert result["by_expected_value"] > result["by_probability"]
    assert result["by_probability"] > result["random"]
    assert result["nobody"] == 0.0
