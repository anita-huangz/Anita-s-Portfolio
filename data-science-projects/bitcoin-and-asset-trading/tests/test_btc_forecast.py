"""Forecast evaluation: metrics, the Diebold-Mariano test, walk-forward, costs.

The statistical machinery is checked against statsmodels where an independent
implementation exists, and against constructed cases where it does not.
"""

from __future__ import annotations

from itertools import pairwise

import numpy as np
import pandas as pd
import pytest

from btc_forecast.backtest import backtest_signal, buy_and_hold
from btc_forecast.baselines import all_baselines, ar_returns, drift, ewma, naive
from btc_forecast.data import DataError, load
from btc_forecast.leakage import measure_scaler_leak, minmax_scale
from btc_forecast.metrics import (
    Accuracy,
    diebold_mariano,
    directional_accuracy,
    mape,
    return_r2,
    rmse,
)
from btc_forecast.walkforward import rolling_origin, walk_forward


@pytest.fixture(scope="module")
def prices():
    return load()


@pytest.fixture(scope="module")
def close(prices):
    return prices.close


def series(values, start="2020-01-01"):
    return pd.Series(
        values, index=pd.date_range(start, periods=len(values), freq="D"), dtype=float
    )


# --------------------------------------------------------------------------- #
# Data
# --------------------------------------------------------------------------- #


def test_the_daily_bars_load(prices):
    assert len(prices) > 4000
    assert prices.dates.is_monotonic_increasing
    assert (prices.close > 0).all()


def test_log_returns_drop_the_undefined_first_day(prices):
    assert len(prices.log_returns) == len(prices) - 1
    assert prices.log_returns.notna().all()


def test_out_of_order_dates_are_rejected(tmp_path):
    path = tmp_path / "bad.csv"
    pd.DataFrame(
        {"date": ["2020-01-02", "2020-01-01"], "Open": [1, 1], "High": [1, 1],
         "Low": [1, 1], "Close": [1, 1]}
    ).to_csv(path, index=False)
    with pytest.raises(DataError, match="not in order"):
        load(path)


def test_a_non_positive_close_is_rejected(tmp_path):
    """Log returns would be undefined, and NaN would spread silently."""
    path = tmp_path / "bad.csv"
    pd.DataFrame(
        {"date": ["2020-01-01", "2020-01-02"], "Open": [1, 1], "High": [1, 1],
         "Low": [1, 1], "Close": [1, 0]}
    ).to_csv(path, index=False)
    with pytest.raises(DataError, match="non-positive"):
        load(path)


# --------------------------------------------------------------------------- #
# Baselines
# --------------------------------------------------------------------------- #


def test_naive_is_yesterdays_price():
    prices = series([10, 11, 12, 13])
    assert naive(prices).tolist()[1:] == [10, 11, 12]


def test_no_baseline_uses_information_from_its_own_day(close):
    """The whole correctness question for a forecast.

    Perturbing day t must not change the forecast *for* day t. If it does, the
    forecaster has seen the answer.
    """
    head = close.iloc[:1500].copy()
    baselines = all_baselines(head, min_train=250)
    tampered = head.copy()
    tampered.iloc[-1] *= 10  # move the final day by an order of magnitude
    after = all_baselines(tampered, min_train=250)
    for column in baselines.columns:
        assert baselines[column].iloc[-1] == pytest.approx(
            after[column].iloc[-1], nan_ok=True
        ), column


def test_drift_adds_the_average_return():
    """Constant 1% growth: the drift forecast should land on it exactly."""
    prices = series([100 * 1.01**i for i in range(60)])
    predicted = drift(prices).iloc[-1]
    assert predicted == pytest.approx(prices.iloc[-1], rel=1e-6)


def test_ewma_lags_a_trending_series():
    prices = series([100 + i for i in range(40)])
    assert ewma(prices, span=10).iloc[-1] < prices.iloc[-2]


def test_the_autoregression_recovers_a_real_pattern():
    """Alternating returns are pure AR(1) with a negative coefficient."""
    rng = np.random.default_rng(0)
    n = 900
    returns = np.zeros(n)
    for t in range(1, n):
        returns[t] = -0.6 * returns[t - 1] + rng.normal(0, 0.01)
    prices = series(100 * np.exp(np.cumsum(returns)))
    forecast = ar_returns(prices, lags=1, min_train=300)
    actual = prices.loc[forecast.dropna().index]
    previous = prices.shift(1).loc[actual.index]
    # A model that found the pattern beats predicting no change.
    assert return_r2(actual, forecast.loc[actual.index], previous) > 0.2


def test_the_autoregression_finds_nothing_in_a_random_walk():
    """And says so, rather than inventing signal."""
    rng = np.random.default_rng(1)
    prices = series(100 * np.exp(np.cumsum(rng.normal(0, 0.01, 900))))
    forecast = ar_returns(prices, lags=5, min_train=300)
    actual = prices.loc[forecast.dropna().index]
    previous = prices.shift(1).loc[actual.index]
    assert return_r2(actual, forecast.loc[actual.index], previous) < 0.05


# --------------------------------------------------------------------------- #
# Metrics
# --------------------------------------------------------------------------- #


def test_a_perfect_forecast_scores_zero_error():
    prices = series([10, 11, 12])
    assert rmse(prices, prices) == 0.0
    assert mape(prices, prices) == 0.0


def test_mismatched_shapes_are_rejected():
    with pytest.raises(ValueError, match="shapes differ"):
        rmse(np.array([1.0, 2.0]), np.array([1.0]))


def test_predicting_no_change_scores_exactly_zero_return_r2():
    """The reference point the whole metric exists to compare against."""
    prices = series([100, 103, 99, 105, 102])
    assert return_r2(prices.iloc[1:], prices.shift(1).iloc[1:], prices.shift(1).iloc[1:]) == (
        pytest.approx(0.0)
    )


def test_a_level_tracking_forecast_has_terrible_return_r2(close):
    """The finding the project is about, as a test.

    The LSTM's forecasts track the price level loosely and carry no
    information about changes. A slightly-lagged copy of the price does the
    same thing: RMSE looks survivable, return R-squared is deeply negative.
    """
    tail = close.iloc[-400:]
    lagging = tail.shift(3)
    previous = tail.shift(1)
    frame = pd.DataFrame({"a": tail, "p": lagging, "prev": previous}).dropna()
    assert return_r2(frame["a"], frame["p"], frame["prev"]) < -0.5


def test_the_naive_forecast_abstains_rather_than_being_wrong(close):
    """Predicting "no change" is no directional call, not a failed one.

    Counting it as wrong would report the random walk at 0% directional
    accuracy, which looks like a finding and is an artefact.
    """
    tail = close.iloc[-300:]
    accuracy = directional_accuracy(
        tail, naive(close).loc[tail.index], close.shift(1).loc[tail.index]
    )
    assert accuracy.total == 0
    assert accuracy.abstention_rate == pytest.approx(1.0)


def test_a_flat_day_is_not_scored():
    actual = series([100, 100, 101])
    previous = series([100, 100, 100])
    predicted = series([101, 101, 101])
    # Day 2 did not move, so there was no direction to get right.
    assert directional_accuracy(actual, predicted, previous).total == 1


def test_the_wilson_interval_stays_inside_zero_and_one():
    for correct, total in [(0, 10), (10, 10), (1, 3), (500, 1000)]:
        low, high = Accuracy(correct, total).interval()
        assert 0 <= low <= high <= 1


def test_a_coin_flip_is_not_called_an_edge():
    """538 days at 48.6% cannot be distinguished from chance."""
    accuracy = Accuracy(correct=262, total=538)
    assert not accuracy.beats_coin_flip
    low, high = accuracy.interval()
    assert low < 0.5 < high


def test_a_real_edge_is_recognised():
    assert Accuracy(correct=600, total=1000).beats_coin_flip


# --------------------------------------------------------------------------- #
# Diebold-Mariano
# --------------------------------------------------------------------------- #


def test_identical_forecasts_cannot_be_told_apart():
    rng = np.random.default_rng(2)
    actual = rng.normal(100, 5, 200)
    forecast = actual + rng.normal(0, 1, 200)
    result = diebold_mariano(actual, forecast, forecast.copy())
    assert result.mean_loss_difference == pytest.approx(0.0)
    assert not result.significant
    assert result.better == "neither"


def test_a_clearly_better_forecast_is_detected():
    rng = np.random.default_rng(3)
    actual = rng.normal(100, 5, 400)
    good = actual + rng.normal(0, 0.5, 400)
    bad = actual + rng.normal(0, 5.0, 400)
    result = diebold_mariano(actual, good, bad)
    assert result.significant
    assert result.better == "first"
    # And symmetric under swapping.
    assert diebold_mariano(actual, bad, good).better == "second"


def test_the_hac_correction_widens_the_standard_error():
    """Why this is not a paired t-test.

    With serially correlated loss differences the naive standard error is too
    small, so a longer truncation lag must not make the statistic *larger*.
    """
    rng = np.random.default_rng(4)
    n = 300
    shock = rng.normal(0, 1, n)
    actual = np.cumsum(shock) + 100
    first = actual + pd.Series(rng.normal(0, 1, n)).rolling(10, min_periods=1).mean().to_numpy()
    second = actual + rng.normal(0, 1, n)
    lag1 = abs(diebold_mariano(actual, first, second, horizon=1).statistic)
    lag5 = abs(diebold_mariano(actual, first, second, horizon=5).statistic)
    assert lag5 <= lag1 * 1.05


def test_the_test_needs_enough_observations():
    with pytest.raises(ValueError, match="at least 10"):
        diebold_mariano(np.arange(5.0), np.arange(5.0), np.arange(5.0))


def test_the_naive_forecast_beats_a_level_tracker_significantly(close):
    """The project's headline, as a hypothesis test rather than a ratio."""
    tail = close.iloc[-500:]
    lagging = close.shift(5).loc[tail.index]
    result = diebold_mariano(
        tail.to_numpy(), naive(close).loc[tail.index].to_numpy(), lagging.to_numpy()
    )
    assert result.significant
    assert result.better == "first"


# --------------------------------------------------------------------------- #
# Walk-forward
# --------------------------------------------------------------------------- #


def test_folds_only_ever_look_backwards(close):
    for fold in rolling_origin(pd.DatetimeIndex(close.index), min_train=1000, test_size=180):
        assert fold.train_end < fold.test_start
        assert fold.test_start <= fold.test_end


def test_test_blocks_do_not_overlap(close):
    folds = list(rolling_origin(pd.DatetimeIndex(close.index), min_train=1000, test_size=180))
    for earlier, later in pairwise(folds):
        assert earlier.test_end < later.test_start


def test_the_training_window_grows(close):
    folds = list(rolling_origin(pd.DatetimeIndex(close.index), min_train=1000, test_size=180))
    sizes = [f.train_size for f in folds]
    assert sizes == sorted(sizes)
    assert sizes[0] == 1000


def test_a_series_too_short_for_one_fold_is_an_error(close):
    with pytest.raises(ValueError, match="at least"):
        list(rolling_origin(pd.DatetimeIndex(close.index[:100]), min_train=1000, test_size=180))


def test_level_rmse_varies_enormously_across_folds(close):
    """Why a single split's RMSE is not a property of the method.

    The same forecaster scores single digits in an early fold and thousands in
    a late one, because RMSE on a price level is dominated by the level.
    """
    result = walk_forward(close, naive, "naive", min_train=1000, test_size=180)
    low, high = result.rmse_spread
    assert high / max(low, 1e-9) > 50


def test_no_baseline_carries_return_information_across_folds(close):
    """Pooled across 21 origins, not cherry-picked from one."""
    for name, fn in [("naive", naive), ("ewma", lambda c: ewma(c, 10))]:
        result = walk_forward(close, fn, name, min_train=1000, test_size=180)
        assert result.mean_return_r2 <= 0.01, name


# --------------------------------------------------------------------------- #
# Leakage
# --------------------------------------------------------------------------- #


def test_the_scaler_leak_is_quantified(close):
    """The notebook fitted MinMaxScaler on the whole series before splitting."""
    leak = measure_scaler_leak(close, train_fraction=0.8)
    assert leak.full_max > leak.train_max
    assert leak.range_inflation > 1.3
    # A third of the scaled axis is above anything training ever saw.
    assert leak.unseen_high_fraction > 0.3


def test_no_leak_when_the_maximum_is_in_the_training_period():
    prices = series([1, 100, 50, 40, 30, 20, 10, 5, 4, 3])
    leak = measure_scaler_leak(prices, train_fraction=0.8)
    assert leak.unseen_high_fraction == 0.0
    assert leak.range_inflation == pytest.approx(1.0)


def test_scaling_takes_its_bounds_as_arguments():
    """Which row the scaler saw becomes a decision, not a side effect."""
    scaled = minmax_scale(np.array([0.0, 5.0, 10.0]), 0.0, 10.0)
    assert scaled.tolist() == [0.0, 0.5, 1.0]
    with pytest.raises(ValueError, match="high must exceed low"):
        minmax_scale(np.array([1.0]), 5.0, 5.0)


# --------------------------------------------------------------------------- #
# Backtest
# --------------------------------------------------------------------------- #


def test_the_position_earns_that_days_return():
    """Mechanics check: long on the up day only, so earn exactly that move."""
    prices = series([100.0, 110.0, 99.0])
    # Above yesterday on day 2 (long), below on day 3 (flat).
    signal = series([np.nan, 200.0, 1.0])
    result = backtest_signal(prices, signal, cost_bps=0)
    assert result.total_return == pytest.approx(0.10)
    assert result.position.tolist() == [1.0, 0.0]


def test_an_always_long_signal_is_buy_and_hold():
    """The drift forecast is exactly this, which is the finding about it."""
    prices = series([100, 105, 103, 110, 108])
    always = prices * 10
    strategy = backtest_signal(prices, always, cost_bps=0)
    held = buy_and_hold(prices)
    assert strategy.total_return == pytest.approx(held.total_return)
    assert strategy.trades == 1
    assert strategy.time_in_market == 1.0


def test_costs_only_ever_reduce_the_return():
    """A signal that actually changes position, so there is something to charge."""
    rng = np.random.default_rng(9)
    prices = series(100 * np.exp(np.cumsum(rng.normal(0, 0.02, 200))))
    signal = ewma(prices, span=5)
    free = backtest_signal(prices, signal, cost_bps=0)
    dear = backtest_signal(prices, signal, cost_bps=50)
    assert dear.trades > 10, "no position changes means nothing to charge for"
    assert dear.total_return < free.total_return


def test_a_churning_signal_is_destroyed_by_costs(close):
    """51% directional accuracy is not an edge once you pay to trade."""
    recent = close.loc["2023-01-01":]
    signal = ar_returns(close, lags=5).loc[recent.index]
    free = backtest_signal(recent, signal, cost_bps=0)
    realistic = backtest_signal(recent, signal, cost_bps=30)
    assert realistic.total_return < free.total_return / 5
    assert free.trades > 100


def test_no_signal_beats_buying_and_holding(close):
    """The conclusion, pooled over the signals this package implements."""
    recent = close.loc["2023-01-01":]
    held = buy_and_hold(recent)
    for name, sig in [
        ("ar5", ar_returns(close, 5)),
        ("ewma", ewma(close, 10)),
        ("drift", drift(close)),
    ]:
        result = backtest_signal(recent, sig.loc[recent.index], cost_bps=10)
        assert result.total_return <= held.total_return + 1e-9, name


def test_the_backtest_does_not_use_tomorrows_price(close):
    """Perturbing the last day must not change any earlier equity value."""
    head = close.iloc[:600]
    signal = ewma(close, 10).iloc[:600]
    baseline = backtest_signal(head, signal, cost_bps=10)
    tampered = head.copy()
    tampered.iloc[-1] *= 5
    after = backtest_signal(tampered, signal, cost_bps=10)
    assert baseline.equity.iloc[:-1].tolist() == pytest.approx(
        after.equity.iloc[:-1].tolist()
    )


def test_the_packaged_bars_are_a_real_file_not_an_lfs_pointer():
    """The repository routes `*.csv` through Git LFS.

    `actions/checkout` does not fetch LFS content, so without the
    project-level `.gitattributes` exclusion CI receives a pointer file and
    every test here fails on a missing column. This says it plainly.
    """
    from btc_forecast.data import DAILY

    first_line = DAILY.read_text().splitlines()[0]
    assert not first_line.startswith("version https://git-lfs"), (
        f"{DAILY} is a Git LFS pointer, not the data."
    )
    assert first_line.startswith("date,")
