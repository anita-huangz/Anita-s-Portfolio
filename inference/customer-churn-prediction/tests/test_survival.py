"""The survival estimators, checked against statsmodels.

Kaplan-Meier, the log-rank test and Cox regression are implemented from
scratch in this project. That is only defensible if the arithmetic is checked
against an independent implementation, so every estimator here is compared
with statsmodels' own -- which is a test dependency and deliberately not a
runtime one.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
from statsmodels.duration.hazard_regression import PHReg
from statsmodels.duration.survfunc import SurvfuncRight, survdiff

from churn.data import cox_design_matrix, load
from churn.survival import (
    concordance_index,
    fit_cox,
    kaplan_meier,
    log_rank_test,
    proportional_hazards_test,
)


@pytest.fixture(scope="module")
def data():
    return load()


@pytest.fixture(scope="module")
def small_design(data):
    """Four columns: enough to be a real fit, quick enough to repeat."""
    return pd.DataFrame(
        {
            "MonthlyCharges": data.frame.MonthlyCharges.to_numpy(float),
            "SeniorCitizen": data.frame.SeniorCitizen.to_numpy(float),
            "is_fiber": (data.frame.InternetService == "Fiber optic").astype(float),
            "two_year": (data.frame.Contract == "Two year").astype(float),
        }
    )


# --------------------------------------------------------------------------- #
# Kaplan-Meier
# --------------------------------------------------------------------------- #


def test_kaplan_meier_matches_statsmodels(data):
    mine = kaplan_meier(data.duration, data.event)
    theirs = SurvfuncRight(data.duration, data.event)
    grid = np.array([1, 3, 6, 12, 24, 36, 48, 60, 72], dtype=float)
    expected = np.array(
        [
            theirs.surv_prob[np.searchsorted(theirs.surv_times, t, "right") - 1]
            for t in grid
        ]
    )
    assert mine.predict(grid) == pytest.approx(expected, abs=1e-12)


def test_the_curve_only_falls(data):
    km = kaplan_meier(data.duration, data.event)
    assert np.all(np.diff(km.survival) <= 0)
    assert km.survival.max() <= 1.0
    assert km.survival.min() >= 0.0


def test_survival_is_one_before_the_first_event(data):
    km = kaplan_meier(data.duration, data.event)
    assert km.predict(0)[0] == 1.0


def test_a_censored_row_is_not_a_failure():
    """The whole reason for this estimator.

    Two customers observed for five months, one of whom left. Naively that is
    a 50% churn rate. The survival curve says the same at t=5, but the
    censored customer keeps contributing to the at-risk count until then
    rather than being dropped or counted as a loss.
    """
    km = kaplan_meier(np.array([5.0, 5.0]), np.array([1, 0]))
    assert km.predict(5)[0] == pytest.approx(0.5)
    assert km.at_risk[0] == 2


def test_everyone_censored_means_a_flat_curve():
    km = kaplan_meier(np.array([1.0, 2.0, 3.0]), np.array([0, 0, 0]))
    assert km.times.size == 0
    assert km.predict(10)[0] == 1.0
    assert km.median_survival == float("inf")


def test_the_median_is_infinite_when_most_customers_remain(data):
    """Not a bug: more than half are still subscribed at the cutoff.

    Quoting a finite median here would mean inventing the part of the curve
    that has not happened.
    """
    km = kaplan_meier(data.duration, data.event)
    assert km.predict(72)[0] > 0.5
    assert km.median_survival == float("inf")


def test_restricted_mean_is_usable_when_the_median_is_not(data):
    km = kaplan_meier(data.duration, data.event)
    rmst = km.restricted_mean(60)
    assert 0 < rmst < 60
    # Longer horizon can only accumulate more expected time.
    assert km.restricted_mean(72) >= rmst


def test_restricted_mean_of_a_curve_that_never_drops():
    km = kaplan_meier(np.array([10.0, 20.0]), np.array([0, 0]))
    assert km.restricted_mean(12) == pytest.approx(12.0)


def test_confidence_intervals_stay_inside_zero_and_one(data):
    """A plain S +- 1.96 SE band escapes [0, 1] in the tails."""
    km = kaplan_meier(data.duration, data.event)
    lower, upper = km.confidence_interval()
    assert np.all(lower >= 0) and np.all(upper <= 1)
    assert np.all(lower <= km.survival + 1e-12)
    assert np.all(upper >= km.survival - 1e-12)


def test_kaplan_meier_rejects_mismatched_input():
    with pytest.raises(ValueError):
        kaplan_meier(np.array([1.0, 2.0]), np.array([1]))
    with pytest.raises(ValueError):
        kaplan_meier(np.array([]), np.array([]))


# --------------------------------------------------------------------------- #
# Log-rank
# --------------------------------------------------------------------------- #


def test_log_rank_matches_statsmodels(data):
    group = data.frame.Contract.to_numpy()
    mine = log_rank_test(data.duration, data.event, group)
    chisq, _ = survdiff(data.duration, data.event, group)
    assert mine.statistic == pytest.approx(chisq, rel=1e-9)


def test_log_rank_on_two_groups_matches_statsmodels(data):
    group = (data.frame.InternetService == "Fiber optic").to_numpy()
    mine = log_rank_test(data.duration, data.event, group)
    chisq, _ = survdiff(data.duration, data.event, group.astype(int))
    assert mine.statistic == pytest.approx(chisq, rel=1e-9)
    assert mine.degrees_of_freedom == 1


def test_contract_length_separates_the_curves(data):
    result = log_rank_test(data.duration, data.event, data.frame.Contract.to_numpy())
    assert result.significant
    assert result.p_value < 1e-50


def test_identical_groups_are_not_significant():
    rng = np.random.default_rng(0)
    duration = rng.integers(1, 40, 600).astype(float)
    event = rng.integers(0, 2, 600)
    group = rng.integers(0, 2, 600)  # unrelated to the outcome
    assert log_rank_test(duration, event, group).p_value > 0.01


def test_log_rank_needs_two_groups(data):
    with pytest.raises(ValueError, match="two groups"):
        log_rank_test(data.duration, data.event, np.zeros(len(data)))


# --------------------------------------------------------------------------- #
# Cox regression
# --------------------------------------------------------------------------- #


def test_cox_coefficients_match_statsmodels(small_design, data):
    mine = fit_cox(small_design, data.duration, data.event)
    theirs = PHReg(
        data.duration, small_design.to_numpy(float), status=data.event, ties="efron"
    ).fit()
    assert mine.coefficients == pytest.approx(theirs.params, abs=1e-8)
    assert mine.standard_errors == pytest.approx(theirs.bse, abs=1e-8)
    assert mine.log_likelihood == pytest.approx(theirs.llf, rel=1e-10)


def test_cox_p_values_match_statsmodels(small_design, data):
    mine = fit_cox(small_design, data.duration, data.event)
    theirs = PHReg(
        data.duration, small_design.to_numpy(float), status=data.event, ties="efron"
    ).fit()
    assert mine.p_values == pytest.approx(theirs.pvalues, abs=1e-8)


def test_the_full_design_matches_statsmodels(data):
    """Twenty covariates, not four: the tie handling has more work to do."""
    X = cox_design_matrix(data)
    mine = fit_cox(X, data.duration, data.event)
    theirs = PHReg(
        data.duration, X.to_numpy(float), status=data.event, ties="efron"
    ).fit()
    assert mine.coefficients == pytest.approx(theirs.params, abs=1e-7)
    assert mine.converged


def test_efron_is_not_breslow(small_design, data):
    """Tenure is whole months, so ties are the rule rather than the exception.

    If the two tie corrections agreed here, using the more involved one would
    be pointless. They do not.
    """
    mine = fit_cox(small_design, data.duration, data.event)
    breslow = PHReg(
        data.duration, small_design.to_numpy(float), status=data.event, ties="breslow"
    ).fit()
    assert np.max(np.abs(mine.coefficients - breslow.params)) > 1e-3


def test_a_singular_design_names_the_problem_rather_than_crashing(data):
    """numpy would say "Singular matrix" and leave you to find out why."""
    X = cox_design_matrix(data)
    X = X.assign(copy_of_contract=X["Contract"])
    with pytest.raises(ValueError, match="rank"):
        fit_cox(X, data.duration, data.event)


def test_cox_needs_at_least_one_event(small_design, data):
    with pytest.raises(ValueError, match="no events"):
        fit_cox(small_design, data.duration, np.zeros_like(data.event))


def test_a_longer_contract_lowers_the_hazard(data):
    """Direction, not just magnitude: a hazard ratio below 1 means safer."""
    X = cox_design_matrix(data)
    model = fit_cox(X, data.duration, data.event)
    summary = model.summary()
    assert summary.loc["Contract", "hazard_ratio"] < 1
    assert summary.loc["Contract", "hr_upper"] < 1  # and significantly so


def test_predicted_survival_curves_fall_and_stay_in_range(data, small_design):
    model = fit_cox(small_design, data.duration, data.event)
    times = np.arange(1, 73, dtype=float)
    curves = model.predict_survival(small_design.head(50), times)
    assert curves.shape == (50, len(times))
    assert np.all((curves >= 0) & (curves <= 1))
    assert np.all(np.diff(curves, axis=1) <= 1e-12)


def test_a_riskier_customer_has_a_lower_curve(data, small_design):
    model = fit_cox(small_design, data.duration, data.event)
    times = np.array([12.0, 24.0])
    risk = model.risk_score(small_design)
    safest, riskiest = np.argmin(risk), np.argmax(risk)
    curves = model.predict_survival(small_design.iloc[[safest, riskiest]], times)
    assert np.all(curves[0] > curves[1])


def test_predicting_before_fitting_a_baseline_is_an_error(small_design, data):
    model = fit_cox(small_design, data.duration, data.event)
    model.baseline_times = np.array([])
    with pytest.raises(ValueError, match="baseline"):
        model.predict_survival(small_design.head(1), np.array([12.0]))


# --------------------------------------------------------------------------- #
# Concordance
# --------------------------------------------------------------------------- #


def test_a_perfect_ranking_scores_one():
    duration = np.array([1.0, 2.0, 3.0, 4.0])
    event = np.array([1, 1, 1, 1])
    assert concordance_index(-duration, duration, event) == pytest.approx(1.0)


def test_a_reversed_ranking_scores_zero():
    duration = np.array([1.0, 2.0, 3.0, 4.0])
    event = np.array([1, 1, 1, 1])
    assert concordance_index(duration, duration, event) == pytest.approx(0.0)


def test_a_constant_score_is_a_coin_flip():
    duration = np.array([1.0, 2.0, 3.0, 4.0])
    event = np.array([1, 1, 1, 1])
    assert concordance_index(np.zeros(4), duration, event) == pytest.approx(0.5)


def test_incomparable_pairs_are_excluded_not_guessed():
    """Two customers still subscribed tell us nothing about their order."""
    assert np.isnan(concordance_index(np.array([1.0, 2.0]), np.array([5.0, 6.0]), np.array([0, 0])))


def test_the_cox_model_ranks_better_than_the_classifier_does(data):
    """The point of the whole exercise, as a number.

    The classifier reaches about 0.845 AUC. The Cox model sees *when* each
    customer left, and the extra information shows up in the ranking.
    """
    X = cox_design_matrix(data)
    model = fit_cox(X, data.duration, data.event)
    c = concordance_index(model.risk_score(X), data.duration, data.event)
    assert c > 0.85


# --------------------------------------------------------------------------- #
# The assumption
# --------------------------------------------------------------------------- #


def test_the_proportional_hazards_assumption_is_checked_and_fails(data):
    """Reported rather than assumed.

    Most of these covariates' effects change with tenure, so their single
    hazard ratio is an average over a moving target. That is worth saying out
    loud next to the table of ratios.
    """
    X = cox_design_matrix(data)
    model = fit_cox(X, data.duration, data.event)
    test = proportional_hazards_test(model, X, data.duration, data.event)
    assert not test.holds
    assert len(test.violations) > 5
    assert set(test.violations) <= set(model.names)


def test_the_assumption_holds_on_data_built_to_satisfy_it():
    """A test that only ever fails is not a test."""
    rng = np.random.default_rng(3)
    n = 1500
    x = rng.normal(size=n)
    # Exponential times: a constant baseline hazard scaled by exp(beta x) is
    # proportional hazards by construction.
    duration = rng.exponential(scale=np.exp(-0.7 * x))
    event = np.ones(n, dtype=int)
    X = pd.DataFrame({"x": x})
    model = fit_cox(X, duration, event)
    assert model.coefficients[0] == pytest.approx(0.7, abs=0.15)
    assert proportional_hazards_test(model, X, duration, event).holds
