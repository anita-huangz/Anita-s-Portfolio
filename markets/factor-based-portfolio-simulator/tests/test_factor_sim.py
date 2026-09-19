"""Tests for scoring, weighting, the backtest loop, and the metrics."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from factor_sim import (
    LowVolatilityFactor,
    MomentumFactor,
    Portfolio,
    RankBasedOptimizer,
    SizeFactor,
    ValueFactor,
    get_factors,
    max_drawdown,
    performance_metrics,
    point_in_time_exposures,
    run_backtest,
    score_universe,
    zscore,
)
from factor_sim.attribution import align, attribute
from factor_sim.metrics import (
    benchmark_metrics,
    drawdown_periods,
    format_metrics,
    turnover,
)


def price_frame(series: dict[str, list[float]], start: str = "2021-01-04") -> pd.DataFrame:
    length = len(next(iter(series.values())))
    return pd.DataFrame(series, index=pd.bdate_range(start=start, periods=length))


# --------------------------------------------------------------------------- #
# Factor orientation and scaling
# --------------------------------------------------------------------------- #


def test_value_prefers_a_lower_pe():
    scores = ValueFactor().raw(pd.Series({"CHEAP": 5.0, "RICH": 50.0}))
    assert scores["CHEAP"] > scores["RICH"]


def test_negative_pe_is_excluded_not_ranked_as_cheap():
    """A loss-making company has no meaningful cheapness signal."""
    scores = ValueFactor().raw(pd.Series({"LOSS": -10.0, "OK": 20.0}))
    assert pd.isna(scores["LOSS"])
    assert not pd.isna(scores["OK"])


def test_size_prefers_smaller_and_uses_logs():
    scores = SizeFactor().raw(pd.Series({"SMALL": 1e9, "MEGA": 3e12}))
    assert scores["SMALL"] > scores["MEGA"]
    # Log-scaled, so the gap is single digits rather than in the trillions.
    assert abs(scores["SMALL"] - scores["MEGA"]) < 20


def test_low_volatility_prefers_calmer_names():
    scores = LowVolatilityFactor().raw(pd.Series({"CALM": 0.10, "WILD": 0.80}))
    assert scores["CALM"] > scores["WILD"]


def test_momentum_passes_returns_through():
    scores = MomentumFactor().raw(pd.Series({"UP": 0.5, "DOWN": -0.2}))
    assert scores["UP"] > scores["DOWN"]


def test_get_factors_rejects_an_unknown_name():
    with pytest.raises(ValueError, match="unknown factor"):
        get_factors(["momentum", "vibes"])


# --------------------------------------------------------------------------- #
# z-scoring
# --------------------------------------------------------------------------- #


def test_zscore_centres_and_scales():
    result = zscore(pd.Series([1.0, 2.0, 3.0]))
    assert result.mean() == pytest.approx(0.0, abs=1e-12)
    assert result.std(ddof=0) == pytest.approx(1.0)


def test_zscore_of_a_flat_cross_section_is_zero_not_nan():
    assert list(zscore(pd.Series([5.0, 5.0, 5.0]))) == [0.0, 0.0, 0.0]


def test_zscore_of_a_single_name_is_zero():
    assert list(zscore(pd.Series([7.0]))) == [0.0]


def test_zscore_fills_missing_values_with_the_mean():
    result = zscore(pd.Series([1.0, np.nan, 3.0]))
    assert result.iloc[1] == 0.0


def test_scoring_puts_factors_on_a_comparable_scale():
    """Raw 1/PE is ~0.03 and momentum is ~0.4; summing them raw lets momentum win.

    After z-scoring, a name that is best on value and worst on momentum should
    not be beaten purely because momentum has a bigger raw magnitude.
    """
    exposures = pd.DataFrame(
        {
            "PE": [5.0, 50.0],          # A is far cheaper
            "Momentum12M": [0.30, 0.50],  # B is modestly ahead
        },
        index=["A", "B"],
    )
    scores = score_universe(exposures, [ValueFactor(), MomentumFactor()])
    # Each factor contributes +/-1 z, so the cheap name is not swamped.
    assert scores["A"] == pytest.approx(0.0, abs=1e-9)
    assert scores["B"] == pytest.approx(0.0, abs=1e-9)


def test_scoring_ignores_a_factor_whose_column_is_absent():
    exposures = pd.DataFrame({"Momentum12M": [0.1, 0.5]}, index=["A", "B"])
    scores = score_universe(exposures, [ValueFactor(), MomentumFactor()])
    assert scores["B"] > scores["A"]


def test_scoring_an_empty_universe_returns_empty():
    assert score_universe(pd.DataFrame(), [MomentumFactor()]).empty


# --------------------------------------------------------------------------- #
# Optimizer
# --------------------------------------------------------------------------- #


def test_top_n_selected_and_equally_weighted():
    weights = RankBasedOptimizer(top_n=2).optimize(
        pd.Series({"A": 3.0, "B": 2.0, "C": 1.0})
    )
    assert set(weights) == {"A", "B"}
    assert all(w == pytest.approx(0.5) for w in weights.values())


def test_negative_scores_still_produce_valid_long_only_weights():
    """Score-proportional weighting flipped signs here and shorted the book."""
    weights = RankBasedOptimizer(top_n=3).optimize(
        pd.Series({"A": -0.5, "B": -1.5, "C": -2.5})
    )
    assert all(w > 0 for w in weights.values())
    assert sum(weights.values()) == pytest.approx(1.0)


def test_scores_summing_to_zero_do_not_divide_by_zero():
    weights = RankBasedOptimizer(top_n=2).optimize(pd.Series({"A": 1.0, "B": -1.0}))
    assert sum(weights.values()) == pytest.approx(1.0)


def test_rank_scheme_weights_the_best_name_most():
    weights = RankBasedOptimizer(top_n=3, scheme="rank").optimize(
        pd.Series({"A": 3.0, "B": 2.0, "C": 1.0})
    )
    assert weights["A"] > weights["B"] > weights["C"]
    assert sum(weights.values()) == pytest.approx(1.0)


def test_weights_always_sum_to_one():
    for scheme in ("equal", "rank"):
        weights = RankBasedOptimizer(top_n=3, scheme=scheme).optimize(
            pd.Series({"A": 1.0, "B": 2.0, "C": 3.0, "D": 4.0})
        )
        assert sum(weights.values()) == pytest.approx(1.0)


def test_fewer_names_than_top_n_is_handled():
    weights = RankBasedOptimizer(top_n=10).optimize(pd.Series({"A": 1.0}))
    assert weights == {"A": pytest.approx(1.0)}


def test_all_nan_scores_produce_no_weights():
    assert RankBasedOptimizer().optimize(pd.Series({"A": np.nan})) == {}


def test_ties_break_deterministically():
    tied = pd.Series({"C": 1.0, "A": 1.0, "B": 1.0})
    first = RankBasedOptimizer(top_n=2).optimize(tied)
    second = RankBasedOptimizer(top_n=2).optimize(tied.sample(frac=1, random_state=7))
    assert set(first) == set(second)


def test_invalid_optimizer_configuration_is_rejected():
    with pytest.raises(ValueError):
        RankBasedOptimizer(top_n=0)
    with pytest.raises(ValueError):
        RankBasedOptimizer(scheme="magic")


# --------------------------------------------------------------------------- #
# Portfolio
# --------------------------------------------------------------------------- #


def test_rebalance_conserves_value_without_costs():
    portfolio = Portfolio(cash=10_000.0)
    prices = {"A": 100.0, "B": 50.0}
    portfolio.rebalance({"A": 0.5, "B": 0.5}, prices)
    assert portfolio.value(prices) == pytest.approx(10_000.0)


def test_unallocated_weight_remains_in_cash():
    """Cash was previously forced to zero, fabricating value."""
    portfolio = Portfolio(cash=10_000.0)
    portfolio.rebalance({"A": 0.5}, {"A": 100.0})
    assert portfolio.cash == pytest.approx(5_000.0)
    assert portfolio.value({"A": 100.0}) == pytest.approx(10_000.0)


def test_transaction_costs_reduce_value():
    portfolio = Portfolio(cash=10_000.0, cost_bps=10.0)
    cost = portfolio.rebalance({"A": 1.0}, {"A": 100.0})
    assert cost == pytest.approx(10.0)
    assert portfolio.value({"A": 100.0}) == pytest.approx(9_990.0)


def test_value_tracks_price_moves():
    portfolio = Portfolio(cash=1_000.0)
    portfolio.rebalance({"A": 1.0}, {"A": 100.0})
    assert portfolio.value({"A": 110.0}) == pytest.approx(1_100.0)


def test_rebalancing_an_empty_portfolio_is_a_noop():
    assert Portfolio(cash=0.0).rebalance({"A": 1.0}, {"A": 10.0}) == 0.0


# --------------------------------------------------------------------------- #
# Point-in-time exposures -- the look-ahead fix
# --------------------------------------------------------------------------- #


def test_exposures_ignore_everything_after_the_as_of_date():
    """The original computed factors from the whole sample and reused them."""
    rising = [100.0 + i for i in range(400)]
    crashing = rising[:300] + [rising[299] * 0.2] * 100
    frame = price_frame({"X": crashing})

    midpoint = frame.index[299]
    early = point_in_time_exposures(frame, midpoint)
    late = point_in_time_exposures(frame, frame.index[-1])

    # As of the midpoint the crash has not happened, so momentum is positive.
    assert early["Momentum12M"]["X"] > 0
    # By the end it is deeply negative. A single full-sample snapshot would have
    # given the same number at both dates.
    assert late["Momentum12M"]["X"] < 0


def test_insufficient_history_yields_nan_not_a_short_window_return():
    frame = price_frame({"X": [100.0 + i for i in range(50)]})
    exposures = point_in_time_exposures(frame, frame.index[-1])
    assert pd.isna(exposures["Momentum12M"]["X"])


def test_static_exposures_are_merged_in():
    frame = price_frame({"X": [100.0] * 300})
    static = pd.DataFrame({"PE": [15.0]}, index=["X"])
    exposures = point_in_time_exposures(frame, frame.index[-1], static)
    assert exposures["PE"]["X"] == 15.0


def test_volatility_is_annualized_and_positive_for_a_moving_series():
    rng = np.random.default_rng(0)
    frame = price_frame({"X": list(100 * np.cumprod(1 + rng.normal(0, 0.01, 300)))})
    exposures = point_in_time_exposures(frame, frame.index[-1])
    assert exposures["Volatility"]["X"] > 0


# --------------------------------------------------------------------------- #
# Backtest loop
# --------------------------------------------------------------------------- #


def growing_universe(days: int = 400) -> pd.DataFrame:
    return price_frame(
        {
            "WIN": [100.0 * (1.001**i) for i in range(days)],
            "MID": [100.0 * (1.0005**i) for i in range(days)],
            "LOSE": [100.0 * (0.999**i) for i in range(days)],
        }
    )


def test_backtest_returns_the_full_nav_path_not_a_tail():
    """`run_simulation` used to return `.tail()`, so metrics saw five rows."""
    prices = growing_universe(400)
    result = run_backtest(prices, get_factors(["momentum"]), top_n=1)
    assert len(result.nav) == len(prices)


def test_nav_starts_at_the_initial_cash():
    result = run_backtest(growing_universe(), get_factors(["momentum"]), initial_cash=50_000.0)
    assert result.nav["NAV"].iloc[0] == pytest.approx(50_000.0)


def test_momentum_strategy_selects_the_rising_name():
    prices = growing_universe(400)
    result = run_backtest(prices, get_factors(["momentum"]), top_n=1)
    last = result.weights.iloc[-1]
    assert last.idxmax() == "WIN"


def test_rebalance_cadence_is_respected():
    prices = growing_universe(200)
    result = run_backtest(prices, get_factors(["momentum"]), rebalance_every=50)
    assert len(result.rebalance_dates) == 4


def test_costs_accumulate_and_reduce_the_final_nav():
    prices = growing_universe(300)
    free = run_backtest(prices, get_factors(["momentum"]), cost_bps=0.0)
    charged = run_backtest(prices, get_factors(["momentum"]), cost_bps=25.0)
    assert charged.total_costs > 0
    assert charged.final_nav < free.final_nav


def test_missing_prices_do_not_break_the_loop():
    prices = growing_universe(300)
    prices.loc[prices.index[100:110], "MID"] = np.nan
    result = run_backtest(prices, get_factors(["momentum"]))
    assert result.nav["NAV"].notna().all()


def test_empty_price_frame_is_rejected():
    with pytest.raises(ValueError, match="empty"):
        run_backtest(pd.DataFrame(), get_factors(["momentum"]))


def test_invalid_cadence_is_rejected():
    with pytest.raises(ValueError, match="rebalance_every"):
        run_backtest(growing_universe(), get_factors(["momentum"]), rebalance_every=0)


def test_backtest_is_deterministic():
    prices = growing_universe(300)
    a = run_backtest(prices, get_factors(["momentum", "low_volatility"]))
    b = run_backtest(prices, get_factors(["momentum", "low_volatility"]))
    assert a.final_nav == pytest.approx(b.final_nav)


# --------------------------------------------------------------------------- #
# Metrics
# --------------------------------------------------------------------------- #


def nav_frame(values: list[float]) -> pd.DataFrame:
    frame = pd.DataFrame(
        {"NAV": values}, index=pd.bdate_range("2021-01-04", periods=len(values))
    )
    frame["Returns"] = frame["NAV"].pct_change()
    return frame


def test_total_return_is_end_over_start():
    assert performance_metrics(nav_frame([100.0, 110.0, 150.0]))[
        "total_return"
    ] == pytest.approx(0.5)


def test_annualized_return_compounds_over_the_right_horizon():
    """Exactly one trading year of data: annualized should equal total."""
    metrics = performance_metrics(nav_frame([100.0] * 251 + [120.0]))
    assert metrics["annualized_return"] == pytest.approx(0.20, rel=1e-3)


def test_metrics_over_a_truncated_frame_differ_from_the_full_path():
    """The original bug: metrics computed on `.tail()` described the last week."""
    full = nav_frame([100.0 * (1.002**i) for i in range(500)])
    assert performance_metrics(full)["total_return"] > performance_metrics(
        full.tail()
    )["total_return"]


def test_max_drawdown_measures_peak_to_trough():
    assert max_drawdown(pd.Series([100.0, 120.0, 60.0, 90.0])) == pytest.approx(0.5)


def test_no_drawdown_on_a_monotonic_rise():
    assert max_drawdown(pd.Series([1.0, 2.0, 3.0])) == pytest.approx(0.0)


def test_flat_nav_has_zero_volatility_and_zero_sharpe():
    metrics = performance_metrics(nav_frame([100.0] * 60))
    assert metrics["volatility"] == pytest.approx(0.0)
    assert metrics["sharpe_ratio"] == 0.0


def test_metrics_reject_an_unusable_frame():
    with pytest.raises(ValueError):
        performance_metrics(pd.DataFrame())
    with pytest.raises(ValueError, match="at least two"):
        performance_metrics(nav_frame([100.0]))


def test_format_metrics_renders_every_field():
    text = format_metrics(performance_metrics(nav_frame([100.0, 105.0, 103.0])))
    for label in ("total return", "Sharpe", "max drawdown", "trading days"):
        assert label in text


# --------------------------------------------------------------------------- #
# Attribution
# --------------------------------------------------------------------------- #


def ff_frame(n: int) -> pd.DataFrame:
    rng = np.random.default_rng(1)
    index = pd.bdate_range("2021-01-04", periods=n)
    return pd.DataFrame(
        {
            "Mkt-RF": rng.normal(0.0004, 0.01, n),
            "SMB": rng.normal(0, 0.005, n),
            "HML": rng.normal(0, 0.005, n),
            "RF": np.full(n, 0.00002),
        },
        index=index,
    )


def test_align_keeps_only_overlapping_dates():
    nav = nav_frame([100.0 * (1.001**i) for i in range(50)])
    merged = align(nav, ff_frame(30))
    assert len(merged) <= 30
    assert "Excess_Return" in merged.columns


def test_align_without_overlap_is_an_explicit_error():
    nav = nav_frame([100.0, 101.0, 102.0])
    ff = ff_frame(10)
    ff.index = pd.bdate_range("2030-01-01", periods=10)
    with pytest.raises(ValueError, match="no overlapping dates"):
        align(nav, ff)


def test_attribution_recovers_a_known_market_beta():
    n = 250
    ff = ff_frame(n)
    beta = 1.5
    returns = ff["RF"] + beta * ff["Mkt-RF"]
    nav_values = 100 * (1 + returns).cumprod()
    nav = pd.DataFrame({"NAV": nav_values.to_numpy()}, index=ff.index)
    nav["Returns"] = returns.to_numpy()

    result = attribute(nav, ff)
    assert result.betas["Mkt-RF"] == pytest.approx(beta, abs=0.05)
    assert result.r_squared > 0.9
    assert "R-squared" in result.render()


def test_attribution_needs_enough_observations():
    nav = nav_frame([100.0, 101.0, 102.0, 103.0])
    with pytest.raises(ValueError, match="observations"):
        attribute(nav, ff_frame(4))


# --------------------------------------------------------------------------- #
# Benchmark-relative metrics
# --------------------------------------------------------------------------- #


def series_from(returns: list[float], start: float = 100.0) -> pd.Series:
    values, level = [], start
    for r in returns:
        level *= 1 + r
        values.append(level)
    return pd.Series(
        [start, *values], index=pd.bdate_range("2021-01-04", periods=len(values) + 1)
    )


def test_a_strategy_identical_to_its_benchmark_has_beta_one_and_no_alpha():
    rng = np.random.default_rng(0)
    moves = list(rng.normal(0.0004, 0.01, 300))
    bench = series_from(moves)
    nav = pd.DataFrame({"NAV": bench.to_numpy()}, index=bench.index)

    m = benchmark_metrics(nav, bench)
    assert m["beta"] == pytest.approx(1.0, abs=1e-6)
    assert m["alpha"] == pytest.approx(0.0, abs=1e-9)
    assert m["tracking_error"] == pytest.approx(0.0, abs=1e-9)
    assert m["excess_total_return"] == pytest.approx(0.0, abs=1e-9)


def test_a_levered_strategy_has_beta_two():
    rng = np.random.default_rng(1)
    moves = list(rng.normal(0.0003, 0.01, 400))
    bench = series_from(moves)
    nav = pd.DataFrame({"NAV": series_from([2 * r for r in moves]).to_numpy()},
                       index=bench.index)
    assert benchmark_metrics(nav, bench)["beta"] == pytest.approx(2.0, abs=0.02)


def test_a_strategy_beaten_by_its_benchmark_reports_negative_excess():
    """The question a standalone return figure cannot answer."""
    rng = np.random.default_rng(2)
    moves = [0.002 + r for r in rng.normal(0, 0.005, 300)]
    bench = series_from(moves)
    # Same shape, consistently weaker.
    nav = pd.DataFrame({"NAV": series_from([r - 0.0008 for r in moves]).to_numpy()},
                       index=bench.index)

    m = benchmark_metrics(nav, bench)
    assert m["strategy_total_return"] > 0      # looks like a winner alone
    assert m["excess_total_return"] < 0        # but lost to the index
    assert m["alpha"] < 0
    assert m["information_ratio"] < 0


def test_capture_ratios_separate_upside_from_downside():
    bench = series_from([0.02, -0.02, 0.02, -0.02] * 40)
    # Follows the upside fully, only half the downside.
    nav = pd.DataFrame(
        {"NAV": series_from([0.02, -0.01, 0.02, -0.01] * 40).to_numpy()},
        index=bench.index,
    )
    m = benchmark_metrics(nav, bench)
    assert m["up_capture"] == pytest.approx(1.0, abs=0.05)
    assert m["down_capture"] == pytest.approx(0.5, abs=0.05)


def test_benchmark_metrics_refuse_too_little_overlap():
    bench = series_from([0.01] * 10)
    nav = pd.DataFrame({"NAV": bench.to_numpy()}, index=bench.index)
    with pytest.raises(ValueError, match="30 overlapping"):
        benchmark_metrics(nav, bench)


def test_benchmark_metrics_use_only_shared_dates():
    rng = np.random.default_rng(3)
    # Benchmark covers a longer span than the strategy.
    bench = series_from(list(rng.normal(0, 0.01, 250)))
    short = bench.iloc[:150]
    nav = pd.DataFrame({"NAV": short.to_numpy()}, index=short.index)

    m = benchmark_metrics(nav, bench)
    assert m["overlapping_days"] == len(short) - 1     # one return per date pair
    assert m["beta"] == pytest.approx(1.0, abs=1e-6)   # the shared slice is identical


# --------------------------------------------------------------------------- #
# Drawdown periods
# --------------------------------------------------------------------------- #


def test_drawdown_period_records_peak_trough_and_recovery():
    nav = nav_frame([100, 120, 90, 100, 130])
    periods = drawdown_periods(nav)
    assert len(periods) == 1
    d = periods[0]
    assert d.depth == pytest.approx(0.25)          # 120 -> 90
    assert d.peak_date == nav.index[1]
    assert d.trough_date == nav.index[2]
    assert d.recovered
    assert d.recovery_days is not None


def test_an_unrecovered_drawdown_has_no_recovery_date():
    nav = nav_frame([100, 150, 120, 110])
    d = drawdown_periods(nav)[0]
    assert not d.recovered
    assert d.recovery_days is None
    assert d.depth == pytest.approx((150 - 110) / 150)


def test_drawdowns_are_ranked_deepest_first():
    nav = nav_frame([100, 110, 105, 120, 60, 120, 125])
    periods = drawdown_periods(nav)
    depths = [d.depth for d in periods]
    assert depths == sorted(depths, reverse=True)
    assert depths[0] == pytest.approx(0.5)         # 120 -> 60


def test_drawdown_periods_distinguish_depth_from_duration():
    """A single max-drawdown number cannot separate these two."""
    quick = nav_frame([100, 70, 100] + [100] * 30)
    slow = nav_frame([100, 70] + [72] * 30 + [100])
    assert drawdown_periods(quick)[0].depth == pytest.approx(
        drawdown_periods(slow)[0].depth
    )
    assert drawdown_periods(slow)[0].drawdown_days >= drawdown_periods(quick)[0].drawdown_days


def test_a_monotonic_rise_has_no_drawdowns():
    assert drawdown_periods(nav_frame([100, 110, 120])) == []


def test_drawdown_periods_are_capped():
    values = []
    for i in range(20):
        values += [100 + i, 100 + i - 5, 100 + i]
    assert len(drawdown_periods(nav_frame(values), top=3)) == 3


# --------------------------------------------------------------------------- #
# Turnover
# --------------------------------------------------------------------------- #


def weights_frame(rows: list[dict[str, float]]) -> pd.DataFrame:
    return pd.DataFrame(rows, index=pd.bdate_range("2021-01-04", periods=len(rows), freq="21D"))


def test_holding_the_same_book_is_zero_turnover():
    w = weights_frame([{"A": 0.5, "B": 0.5}] * 4)
    assert turnover(w)["average_turnover"] == pytest.approx(0.0)


def test_replacing_the_book_entirely_is_full_turnover():
    w = weights_frame([{"A": 1.0, "B": 0.0}, {"A": 0.0, "B": 1.0}])
    # One-way: sold all of A and bought all of B, so 100% of the book moved.
    assert turnover(w)["average_turnover"] == pytest.approx(1.0)


def test_turnover_annualises_from_the_rebalance_cadence():
    w = weights_frame([{"A": 1.0, "B": 0.0}, {"A": 0.0, "B": 1.0}] * 6)
    stats = turnover(w)
    assert stats["annualised_turnover"] > stats["average_turnover"]
    assert stats["rebalances"] == 12


def test_turnover_of_a_single_rebalance_is_zero():
    assert turnover(weights_frame([{"A": 1.0}]))["average_turnover"] == 0.0


def test_turnover_handles_a_name_entering_the_universe():
    w = weights_frame([{"A": 1.0}, {"A": 0.5, "B": 0.5}])
    assert turnover(w)["average_turnover"] == pytest.approx(0.5)


def test_turnover_of_an_empty_frame_is_zero():
    assert turnover(pd.DataFrame())["rebalances"] == 0.0
