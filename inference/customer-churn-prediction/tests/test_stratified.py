"""Stratified Cox, and the question of whether it actually helped.

The project already detected that proportional hazards fails here and its
README named stratification as the next step. These tests cover the
implementation and, just as importantly, pin the measured answer to whether
that step worked — because it did not, and a claim like that has to be a test
rather than a sentence.
"""

import numpy as np
import pytest

from churn.data import cox_design_matrix, load
from churn.survival import (
    compare_periods,
    concordance_index,
    fit_cox,
    fit_stratified_cox,
    proportional_hazards_test,
    stratified_proportional_hazards_test,
)


@pytest.fixture(scope="module")
def churn():
    data = load()
    X = cox_design_matrix(data)
    duration = data.frame["tenure"].to_numpy(dtype=float)
    event = (data.frame["Churn"] == "Yes").astype(int).to_numpy()
    contract = data.frame["Contract"].astype(str).to_numpy()
    return X, duration, event, contract


@pytest.fixture(scope="module")
def stratified(churn):
    X, duration, event, contract = churn
    without = X.drop(columns=[c for c in X.columns if c.startswith("Contract")])
    model = fit_stratified_cox(without, duration, event, contract, "Contract")
    return model, without


class TestFit:
    def test_it_converges(self, stratified):
        model, _ = stratified
        assert model.converged

    def test_one_baseline_per_stratum(self, stratified):
        model, _ = stratified
        assert set(model.strata) == {"Month-to-month", "One year", "Two year"}
        assert set(model.baselines) == set(model.strata)
        for times, cumulative in model.baselines.values():
            assert times.size == cumulative.size
            assert np.all(np.diff(cumulative) >= 0), "cumulative hazard must not fall"

    def test_the_stratifying_variable_has_no_coefficient(self, stratified):
        """Its effect is in the baselines; there is nothing left to estimate."""
        model, _ = stratified
        assert not any(name.startswith("Contract") for name in model.names)

    def test_strata_partition_the_rows(self, stratified, churn):
        model, _ = stratified
        _, duration, _, _ = churn
        assert sum(model.stratum_sizes.values()) == len(duration)

    def test_it_fits_better_than_the_unstratified_model(self, churn, stratified):
        """Freeing the baselines has to raise the likelihood; it is strictly
        more flexible. This is a sanity check on the implementation, not
        evidence that stratifying solved anything."""
        X, duration, event, _ = churn
        model, _ = stratified
        plain = fit_cox(X, duration, event)
        assert model.log_likelihood > plain.log_likelihood

    def test_survival_curves_use_each_rows_own_baseline(self, stratified, churn):
        model, without = stratified
        _, _, _, contract = churn
        rows = without.iloc[:3]
        curves = model.predict_survival(rows, np.array([1.0, 12.0, 60.0]), contract[:3])
        assert curves.shape == (3, 3)
        assert np.all((curves >= 0) & (curves <= 1))
        assert np.all(np.diff(curves, axis=1) <= 1e-12), "survival must not rise"


class TestItDidNotFixTheViolation:
    """The measured negative result, pinned so it cannot quietly change."""

    def test_violations_remain_after_stratifying(self, churn, stratified):
        X, duration, event, contract = churn
        model, without = stratified
        before = proportional_hazards_test(fit_cox(X, duration, event), X, duration, event)
        after = stratified_proportional_hazards_test(
            model, without, duration, event, contract
        )
        assert len(before.violations) >= 15
        assert len(after.violations) >= 15, (
            "stratifying on Contract was expected not to resolve the violation"
        )

    def test_the_magnitudes_do_not_shrink(self, churn, stratified):
        """Counting p < 0.05 at this sample size is weak; compare effect sizes."""
        X, duration, event, contract = churn
        model, without = stratified
        before = proportional_hazards_test(fit_cox(X, duration, event), X, duration, event)
        after = stratified_proportional_hazards_test(
            model, without, duration, event, contract
        )
        shared = list(without.columns)
        assert after.correlations[shared].abs().mean() >= (
            before.correlations[shared].abs().mean() * 0.95
        )


class TestPeriodComparison:
    def test_effects_differ_between_early_and_late(self, churn):
        X, duration, event, _ = churn
        periods = compare_periods(X, duration, event, cutoff=12)
        table = periods.table()
        assert periods.early_events > 0 and periods.late_events > 0
        # Contract's protection weakens sharply once a customer has stayed a year.
        assert table.loc["Contract", "ratio"] > 2

    def test_some_effects_reverse_direction(self, churn):
        """The substantive reason PH fails: not weaker, opposite."""
        X, duration, event, _ = churn
        periods = compare_periods(X, duration, event, cutoff=12)
        assert "StreamingTV_Yes" in periods.reversals

    def test_the_early_fit_keeps_everyone(self, churn):
        """Restricting to early churners would condition on the outcome."""
        X, duration, event, _ = churn
        periods = compare_periods(X, duration, event, cutoff=12)
        assert periods.early_events < int(event.sum())
        assert periods.early_events + periods.late_events == int(event.sum())

    def test_a_cutoff_past_every_event_is_an_error(self, churn):
        X, duration, event, _ = churn
        with pytest.raises(ValueError, match="no events after"):
            compare_periods(X, duration, event, cutoff=duration.max() + 1)


class TestGuards:
    def test_strata_and_rows_must_agree(self, churn):
        X, duration, event, _ = churn
        with pytest.raises(ValueError, match="number of rows"):
            fit_stratified_cox(X, duration, event, ["a", "b"])

    def test_no_events_is_an_error(self, churn):
        X, duration, _, contract = churn
        with pytest.raises(ValueError, match="no events"):
            fit_stratified_cox(X, duration, np.zeros(len(duration), int), contract)

    def test_a_stratum_with_no_events_is_dropped_not_crashed(self, churn):
        X, duration, event, contract = churn
        labels = contract.copy()
        quiet = ~event.astype(bool)
        labels[np.flatnonzero(quiet)[:50]] = "no-events-here"
        without = X.drop(columns=[c for c in X.columns if c.startswith("Contract")])
        model = fit_stratified_cox(without, duration, event, labels, "Contract")
        assert "no-events-here" not in model.strata

    def test_leaving_the_stratifying_columns_in_is_caught_when_it_is_singular(
        self, churn
    ):
        """Contract is one column here, so this stays fittable -- the guard that
        matters is the rank check, and it fires on a genuinely singular matrix."""
        X, duration, event, contract = churn
        doubled = X.copy()
        doubled["copy_of_contract"] = doubled["Contract"]
        with pytest.raises(ValueError, match="rank"):
            fit_stratified_cox(doubled, duration, event, contract)


def test_it_still_ranks_within_a_stratum(churn, stratified):
    """The fair comparison, because the two models rank different things.

    The stratified model has no Contract coefficient -- that effect lives in
    the baselines -- so its global risk score must be worse than the plain
    model's, by construction rather than by failing. Inside a single stratum
    every customer shares a baseline, and there the scores are comparable.
    """
    X, duration, event, contract = churn
    model, without = stratified
    plain = fit_cox(X, duration, event)

    for label in model.strata:
        mask = contract == label
        if event[mask].sum() < 30:
            continue
        stratified_c = concordance_index(
            (without[mask].to_numpy(dtype=float) - model.means) @ model.coefficients,
            duration[mask],
            event[mask],
        )
        plain_c = concordance_index(
            (X[mask].to_numpy(dtype=float) - plain.means) @ plain.coefficients,
            duration[mask],
            event[mask],
        )
        assert stratified_c > 0.6, f"{label}: {stratified_c:.3f}"
        # Within a stratum the two should be close; Contract is constant there,
        # so the column the stratified model dropped carries no information.
        assert abs(stratified_c - plain_c) < 0.05, f"{label}: {stratified_c} vs {plain_c}"
