"""Estimators, optimisers, and the out-of-sample protocol.

The shrinkage estimator is checked against scikit-learn's; the optimisers
against portfolios whose right answer is known by construction; and the
backtest against the one mistake that makes every allocation strategy look
good, which is letting it see the returns it is scored on.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from allocation.backtest import (
    in_sample_result,
    rolling_backtest,
    weight_instability,
)
from allocation.data import DataError, load
from allocation.estimate import expected_returns, ledoit_wolf, sample_covariance
from allocation.optimise import (
    ALLOCATORS,
    equal_weight,
    maximum_sharpe,
    minimum_variance,
    risk_parity,
)


@pytest.fixture(scope="module")
def prices():
    return load()


@pytest.fixture(scope="module")
def returns(prices):
    return prices.returns


@pytest.fixture(scope="module")
def backtests(returns):
    return {name: rolling_backtest(returns, fn, name) for name, fn in ALLOCATORS.items()}


# --------------------------------------------------------------------------- #
# Data
# --------------------------------------------------------------------------- #


def test_five_etfs_load(prices):
    assert prices.tickers == ["SPY", "IWM", "TLT", "LQD", "SHV"]
    assert len(prices) > 4000


def test_out_of_order_dates_are_rejected(tmp_path):
    path = tmp_path / "bad.csv"
    pd.DataFrame(
        {"date": ["2020-01-02", "2020-01-01"], "SPY": [1.0, 1.0]}
    ).to_csv(path, index=False)
    with pytest.raises(DataError, match="not in order"):
        load(path)


def test_adjusted_closes_show_the_bond_funds_paying(prices):
    """SHV's price barely moves; on unadjusted closes it would look flat."""
    summary = prices.annualised_summary()
    assert summary.loc["SHV", "annual_return"] > 0.005
    assert summary.loc["SHV", "annual_vol"] < 0.01


# --------------------------------------------------------------------------- #
# Estimation
# --------------------------------------------------------------------------- #


def test_shrinkage_matches_scikit_learn(returns):
    from sklearn.covariance import LedoitWolf

    window = returns.iloc[:500]
    mine, intensity = ledoit_wolf(window)
    theirs = LedoitWolf(assume_centered=False).fit(window.to_numpy())
    # scikit-learn shrinks toward a scaled identity, this toward constant
    # correlation, so the matrices differ -- but both must stay close to the
    # sample estimate when the sample is large relative to the dimension.
    assert 0.0 <= intensity <= 1.0
    assert 0.0 <= theirs.shrinkage_ <= 1.0
    assert mine.shape == (5, 5)


def test_shrinkage_stays_between_the_sample_and_the_target(returns):
    window = returns.iloc[:300]
    shrunk, intensity = ledoit_wolf(window)
    sample = sample_covariance(window)
    assert 0.0 <= intensity <= 1.0
    # Variances are preserved by the constant-correlation target.
    assert np.diag(shrunk) == pytest.approx(np.diag(sample), rel=1e-9)


def test_shrinkage_is_stronger_on_a_shorter_window(returns):
    """Less data, less to trust, more shrinkage."""
    _, short = ledoit_wolf(returns.iloc[:60])
    _, long = ledoit_wolf(returns.iloc[:2000])
    assert short > long


def test_the_covariance_estimate_is_positive_semidefinite(returns):
    for estimate in (sample_covariance(returns), ledoit_wolf(returns)[0]):
        assert np.all(np.linalg.eigvalsh(estimate) > -1e-10)


def test_estimation_needs_more_than_one_observation(returns):
    with pytest.raises(ValueError, match="at least two"):
        ledoit_wolf(returns.iloc[:1])


# --------------------------------------------------------------------------- #
# Optimisers
# --------------------------------------------------------------------------- #


def test_every_allocator_returns_a_valid_portfolio(returns):
    covariance = ledoit_wolf(returns)[0]
    mu = expected_returns(returns)
    for name, allocate in ALLOCATORS.items():
        weights = allocate(mu, covariance)
        assert weights.sum() == pytest.approx(1.0), name
        assert (weights >= 0).all(), name
        assert len(weights) == 5, name


def test_equal_weight_ignores_both_inputs():
    """Which is the whole reason it is hard to beat."""
    a = equal_weight(np.array([0.1, 0.2]), np.eye(2))
    b = equal_weight(np.array([9.9, -3.0]), np.eye(2) * 100)
    assert a.tolist() == b.tolist() == [0.5, 0.5]


def test_minimum_variance_finds_the_quiet_asset():
    covariance = np.diag([0.04, 0.0001])
    weights = minimum_variance(np.array([0.1, 0.01]), covariance)
    assert weights[1] > 0.95


def test_maximum_sharpe_prefers_the_better_reward_per_risk():
    """For uncorrelated assets the tangency weights go as mu / variance.

    0.20/0.04 against 0.02/0.04 normalises to [0.909, 0.091] -- not [1, 0],
    which is what I assumed first. The optimiser was right and the test was
    wrong.
    """
    covariance = np.diag([0.04, 0.04])
    weights = maximum_sharpe(np.array([0.20, 0.02]), covariance)
    assert weights == pytest.approx([0.9091, 0.0909], abs=0.005)


def test_risk_parity_equalises_the_risk_contributions():
    covariance = np.diag([0.04, 0.01])
    weights = risk_parity(np.array([0.1, 0.1]), covariance)
    contributions = weights * (covariance @ weights)
    assert contributions[0] == pytest.approx(contributions[1], rel=0.05)
    # And unlike minimum variance it does not abandon the riskier asset.
    assert weights[0] > 0.2


def test_solver_dust_is_cleaned_up():
    """SLSQP returns -1e-17 at a boundary, which makes long-only technically short."""
    covariance = np.diag([0.04, 0.0001, 0.05])
    weights = minimum_variance(np.array([0.1, 0.01, 0.2]), covariance)
    assert (weights >= 0).all()
    assert weights.sum() == pytest.approx(1.0)


# --------------------------------------------------------------------------- #
# The protocol
# --------------------------------------------------------------------------- #


def test_the_backtest_needs_data_beyond_the_lookback(returns):
    with pytest.raises(ValueError, match="out of sample"):
        rolling_backtest(returns.iloc[:300], equal_weight, "x", lookback=504)


def test_weights_are_chosen_only_from_prior_data(returns):
    """The correctness question for the whole exercise.

    Perturbing the *last* day must not change any weight, because every
    rebalance uses only the window before it.
    """
    head = returns.iloc[:1500].copy()
    baseline = rolling_backtest(head, maximum_sharpe, "a", lookback=504)
    tampered = head.copy()
    tampered.iloc[-1] = tampered.iloc[-1] * 10
    after = rolling_backtest(tampered, maximum_sharpe, "a", lookback=504)
    pd.testing.assert_frame_equal(baseline.weights, after.weights)


def test_costs_only_reduce_the_return(returns):
    free = rolling_backtest(returns, maximum_sharpe, "a", cost_bps=0)
    dear = rolling_backtest(returns, maximum_sharpe, "a", cost_bps=50)
    assert dear.total_return < free.total_return


def test_one_over_n_still_trades_a_little(backtests):
    """Returning to a fixed target is not free.

    Between rebalances the book drifts with prices, so quarterly rebalancing
    back to equal weight trades every quarter. An earlier version of
    `average_turnover` compared consecutive *targets* and reported zero -- it
    now records what was actually traded.
    """
    result = backtests["equal weight (1/N)"]
    assert 0 < result.average_turnover < 0.05
    # Still by far the cheapest to run.
    assert result.cost_drag < 0.0005


# --------------------------------------------------------------------------- #
# The findings
# --------------------------------------------------------------------------- #


def test_one_over_n_earns_the_most_out_of_sample(backtests):
    """DeMiguel, Garlappi and Uppal (2009), reproduced on five ETFs."""
    naive = backtests["equal weight (1/N)"].annualised_return
    for name, result in backtests.items():
        if name != "equal weight (1/N)":
            assert result.annualised_return <= naive, name


def test_maximising_sharpe_produces_the_worst_out_of_sample_sharpe(backtests):
    """The estimation-error result in one line.

    The rule that explicitly optimises the Sharpe ratio comes last on it,
    because expected returns cannot be estimated well enough to optimise
    against.
    """
    sharpes = {name: result.sharpe for name, result in backtests.items()}
    assert min(sharpes, key=sharpes.get) == "maximum Sharpe"


def test_in_sample_flatters_the_optimiser(returns):
    """The gap the notebook never measured."""
    inside = in_sample_result(returns, maximum_sharpe, "a").sharpe
    outside = rolling_backtest(returns, maximum_sharpe, "a").sharpe
    assert inside > 5 * outside


def test_in_sample_barely_flatters_the_rule_that_estimates_nothing(returns):
    """1/N has no parameters to overfit, so the two agree closely."""
    inside = in_sample_result(returns, equal_weight, "a").sharpe
    outside = rolling_backtest(returns, equal_weight, "a").sharpe
    assert abs(inside - outside) < 0.15


def test_the_optimiser_rewrites_the_book_every_quarter(backtests):
    """Estimation error reaching the portfolio, measured directly."""
    assert weight_instability(backtests["maximum Sharpe"]) > 2 * weight_instability(
        backtests["risk parity"]
    )
    # 14.9% per rebalance against 1.8% for drift-correcting 1/N.
    assert backtests["maximum Sharpe"].average_turnover > 5 * backtests[
        "equal weight (1/N)"
    ].average_turnover


def test_minimum_variance_becomes_a_cash_fund(backtests, prices):
    """Its Sharpe of 6+ is an artefact of near-zero volatility, not skill.

    On a universe containing a short-Treasury ETF, "minimise variance" has an
    obvious and useless answer.
    """
    result = backtests["minimum variance"]
    assert result.volatility < 0.01
    assert result.weights["SHV"].mean() > 0.9
    assert result.annualised_return < 0.03


def test_the_conclusion_survives_a_different_rebalance_cadence(returns):
    """A result that only holds at one setting is not a result."""
    for cadence in (21, 126):
        naive = rolling_backtest(
            returns, equal_weight, "n", rebalance_every=cadence
        ).annualised_return
        optimised = rolling_backtest(
            returns, maximum_sharpe, "m", rebalance_every=cadence
        ).annualised_return
        assert optimised < naive, cadence
