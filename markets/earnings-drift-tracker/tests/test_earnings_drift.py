"""Tests for the drift arithmetic and the parsing around it."""

from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd
import pytest

from earnings_drift import EarningsReport, Stock, analyze_drift, drift_for_event
from earnings_drift.drift import (
    hit_rate,
    pool,
    spread_test,
    summarize,
    surprise_buckets,
    surprise_correlation,
)
from earnings_drift.report import format_summary
from earnings_drift.sources import MissingAPIKey, fmp_api_key, parse_surprises


def prices(closes: list[float], start: str = "2023-01-02") -> pd.DataFrame:
    """Business-day close series, so index gaps behave like real weekends."""
    index = pd.bdate_range(start=start, periods=len(closes))
    return pd.DataFrame({"Close": closes}, index=index)


# --------------------------------------------------------------------------- #
# EarningsReport
# --------------------------------------------------------------------------- #


def test_surprise_and_percentage():
    report = EarningsReport.from_iso("2023-02-02", eps_actual=1.20, eps_estimate=1.00)
    assert report.surprise == pytest.approx(0.20)
    assert report.surprise_pct == pytest.approx(20.0)


def test_percentage_uses_absolute_estimate_so_a_beat_stays_positive():
    """A company beating a loss estimate has a positive surprise."""
    report = EarningsReport.from_iso("2023-02-02", eps_actual=-0.50, eps_estimate=-1.00)
    assert report.surprise == pytest.approx(0.50)
    assert report.surprise_pct == pytest.approx(50.0)


def test_zero_estimate_gives_none_not_zero():
    """Reporting 0.0 would plot a real surprise at 'no surprise' and bias the fit."""
    report = EarningsReport.from_iso("2023-02-02", eps_actual=0.30, eps_estimate=0.0)
    assert report.surprise_pct is None


def test_from_iso_rejects_a_bad_date():
    with pytest.raises(ValueError):
        EarningsReport.from_iso("02/02/2023", 1.0, 1.0)


def test_stock_requires_a_close_column():
    with pytest.raises(ValueError, match="Close"):
        Stock("AAPL").set_price_data(pd.DataFrame({"Open": [1.0]}))


def test_stock_sorts_price_data_on_assignment():
    frame = prices([1.0, 2.0, 3.0]).iloc[::-1]
    stock = Stock("AAPL")
    stock.set_price_data(frame)
    assert stock.price_data.index.is_monotonic_increasing


# --------------------------------------------------------------------------- #
# Single-event drift
# --------------------------------------------------------------------------- #


def test_forward_returns_measured_off_the_event_close():
    frame = prices([100.0, 110.0, 120.0, 130.0, 140.0, 150.0])
    report = EarningsReport.from_iso("2023-01-02", 1.1, 1.0)
    row = drift_for_event(frame, report, horizons=(1, 2))
    assert row.returns[1] == pytest.approx(0.10)
    assert row.returns[2] == pytest.approx(0.20)
    assert row.baseline_date == date(2023, 1, 2)


def test_weekend_announcement_falls_back_to_the_prior_session():
    """The old exact-index check dropped every non-trading-day announcement."""
    frame = prices([100.0, 110.0, 121.0], start="2023-01-06")  # Fri, Mon, Tue
    saturday = EarningsReport.from_iso("2023-01-07", 1.1, 1.0)
    row = drift_for_event(frame, saturday, horizons=(1,))
    assert row is not None
    assert row.baseline_date == date(2023, 1, 6)  # Friday
    assert row.returns[1] == pytest.approx(0.10)


def test_event_before_any_price_history_is_skipped():
    frame = prices([100.0, 101.0], start="2023-06-01")
    early = EarningsReport.from_iso("2020-01-01", 1.1, 1.0)
    assert drift_for_event(frame, early, horizons=(1,)) is None


def test_horizon_past_the_end_is_omitted_not_filled():
    """Filling a missing horizon with 0.0 would read as a flat return."""
    frame = prices([100.0, 110.0, 120.0])
    report = EarningsReport.from_iso("2023-01-02", 1.1, 1.0)
    row = drift_for_event(frame, report, horizons=(1, 10))
    assert set(row.returns) == {1}


def test_event_with_no_measurable_horizon_returns_none():
    frame = prices([100.0])
    report = EarningsReport.from_iso("2023-01-02", 1.1, 1.0)
    assert drift_for_event(frame, report, horizons=(1,)) is None


def test_empty_price_frame_returns_none():
    empty = pd.DataFrame({"Close": []}, index=pd.DatetimeIndex([]))
    report = EarningsReport.from_iso("2023-01-02", 1.1, 1.0)
    assert drift_for_event(empty, report) is None


# --------------------------------------------------------------------------- #
# Aggregation
# --------------------------------------------------------------------------- #


def build_stock(n_closes: int = 30) -> Stock:
    stock = Stock("AAPL")
    stock.set_price_data(prices([100.0 + i for i in range(n_closes)]))
    return stock


def test_analyze_produces_one_row_per_measurable_event():
    stock = build_stock()
    stock.add_earnings(EarningsReport.from_iso("2023-01-03", 1.2, 1.0))
    stock.add_earnings(EarningsReport.from_iso("2023-01-10", 0.9, 1.0))
    stock.add_earnings(EarningsReport.from_iso("2019-01-01", 1.0, 1.0))  # too early

    drift = analyze_drift(stock, horizons=(1, 5), pre_window=0)
    assert len(drift) == 2
    assert list(drift.columns) == [
        "event_date", "baseline_date", "surprise_pct", "ticker", "1d", "5d"
    ]


def test_rows_are_sorted_by_event_date_regardless_of_input_order():
    stock = build_stock()
    stock.add_earnings(EarningsReport.from_iso("2023-01-10", 1.0, 1.0))
    stock.add_earnings(EarningsReport.from_iso("2023-01-03", 1.0, 1.0))
    drift = analyze_drift(stock, horizons=(1,))
    assert drift["event_date"].tolist() == [date(2023, 1, 3), date(2023, 1, 10)]


def test_no_events_yields_a_typed_empty_frame_not_a_crash():
    drift = analyze_drift(build_stock(), horizons=(1, 5))
    assert drift.empty
    assert "1d" in drift.columns


def test_analyze_without_price_data_is_an_explicit_error():
    with pytest.raises(ValueError, match="no price data"):
        analyze_drift(Stock("AAPL"))


def test_summarize_does_not_mutate_its_input():
    stock = build_stock()
    stock.add_earnings(EarningsReport.from_iso("2023-01-03", 1.2, 1.0))
    drift = analyze_drift(stock, horizons=(1, 5))
    before = drift.copy(deep=True)
    summarize(drift, horizons=(1, 5))
    pd.testing.assert_frame_equal(drift, before)


def test_summarize_of_an_empty_frame_is_empty():
    assert summarize(pd.DataFrame(), horizons=(1,)).empty


# --------------------------------------------------------------------------- #
# Correlation
# --------------------------------------------------------------------------- #


def test_correlation_needs_at_least_three_pairs():
    two = pd.DataFrame({"surprise_pct": [1.0, 2.0], "1d": [0.01, 0.02]})
    assert surprise_correlation(two) is None


def test_perfectly_monotonic_surprise_and_drift_correlate_at_one():
    frame = pd.DataFrame(
        {"surprise_pct": [-10.0, 0.0, 5.0, 20.0], "1d": [-0.02, 0.0, 0.01, 0.04]}
    )
    assert surprise_correlation(frame) == pytest.approx(1.0, abs=1e-6)


def test_correlation_ignores_rows_with_an_undefined_surprise():
    frame = pd.DataFrame(
        {"surprise_pct": [-10.0, None, 5.0, 20.0], "1d": [-0.02, 0.5, 0.01, 0.04]}
    )
    assert surprise_correlation(frame) == pytest.approx(1.0, abs=1e-6)


def test_correlation_on_a_missing_horizon_is_none():
    assert surprise_correlation(pd.DataFrame({"surprise_pct": [1.0]}), horizon=99) is None


# --------------------------------------------------------------------------- #
# Parsing and configuration
# --------------------------------------------------------------------------- #


def test_parse_skips_incomplete_rows_and_sorts():
    payload = [
        {"date": "2023-05-04", "actualEarningResult": 1.2, "estimatedEarning": 1.0},
        {"date": "2023-02-02", "actualEarningResult": 1.1, "estimatedEarning": 1.0},
        {"date": "2023-08-03", "actualEarningResult": None, "estimatedEarning": 1.0},
        {"date": "2023-11-02", "estimatedEarning": 1.0},
        {"actualEarningResult": 1.0, "estimatedEarning": 1.0},
        {"date": "not-a-date", "actualEarningResult": 1.0, "estimatedEarning": 1.0},
    ]
    reports = parse_surprises(payload)
    assert [r.event_date for r in reports] == [date(2023, 2, 2), date(2023, 5, 4)]


def test_parse_of_an_empty_payload_is_empty():
    assert parse_surprises([]) == []


def test_missing_api_key_names_the_variable(monkeypatch):
    monkeypatch.delenv("FMP_API_KEY", raising=False)
    with pytest.raises(MissingAPIKey, match="FMP_API_KEY"):
        fmp_api_key()


def test_blank_api_key_is_treated_as_missing(monkeypatch):
    monkeypatch.setenv("FMP_API_KEY", "   ")
    with pytest.raises(MissingAPIKey):
        fmp_api_key()


def test_importing_sources_does_not_prompt_or_require_a_key(monkeypatch):
    """Regression: the module used to call input() at import time."""
    monkeypatch.delenv("FMP_API_KEY", raising=False)
    import importlib

    import earnings_drift.sources as sources

    importlib.reload(sources)  # must not raise or block


# --------------------------------------------------------------------------- #
# Reporting
# --------------------------------------------------------------------------- #


def test_summary_of_an_empty_frame_is_a_readable_sentence():
    assert "No measurable" in format_summary(pd.DataFrame())


def test_summary_reports_counts_means_and_correlation():
    stock = build_stock()
    for day, actual in [("2023-01-03", 1.2), ("2023-01-10", 0.8), ("2023-01-17", 1.0)]:
        stock.add_earnings(EarningsReport.from_iso(day, actual, 1.0))
    text = format_summary(analyze_drift(stock, horizons=(1, 5)), horizons=(1, 5))
    assert "3 earnings events" in text
    # Labelled "raw" now that market-adjusted drift is also reported.
    assert "Average raw drift" in text
    assert "correlation" in text.lower()


# --------------------------------------------------------------------------- #
# Market adjustment
# --------------------------------------------------------------------------- #


def test_abnormal_return_strips_out_the_market_move():
    """A stock that exactly tracked the market has zero abnormal return.

    Without this adjustment the project reports beta as if it were drift.
    """
    stock_prices = prices([100.0, 110.0, 120.0])
    bench = prices([200.0, 220.0, 240.0])  # identical percentage moves
    report = EarningsReport.from_iso("2023-01-02", 1.2, 1.0)

    row = drift_for_event(stock_prices, report, horizons=(1, 2), benchmark=bench)
    assert row.returns[1] == pytest.approx(0.10)
    assert row.abnormal[1] == pytest.approx(0.0, abs=1e-12)
    assert row.abnormal[2] == pytest.approx(0.0, abs=1e-12)


def test_abnormal_return_isolates_outperformance():
    stock_prices = prices([100.0, 115.0])
    bench = prices([100.0, 105.0])
    report = EarningsReport.from_iso("2023-01-02", 1.2, 1.0)
    row = drift_for_event(stock_prices, report, horizons=(1,), benchmark=bench)
    assert row.returns[1] == pytest.approx(0.15)
    assert row.abnormal[1] == pytest.approx(0.10)


def test_abnormal_return_survives_a_benchmark_missing_a_session():
    """Aligning by position rather than date would offset the windows."""
    stock_prices = prices([100.0, 110.0, 121.0], start="2023-01-02")
    bench = prices([100.0, 110.0, 121.0], start="2023-01-02").drop(
        pd.Timestamp("2023-01-03")
    )
    report = EarningsReport.from_iso("2023-01-02", 1.2, 1.0)
    row = drift_for_event(stock_prices, report, horizons=(1,), benchmark=bench)
    # The benchmark's next available session is a day later, so the windows
    # differ -- but the baseline is still located by date, not by index slot.
    assert row.baseline_date == date(2023, 1, 2)
    assert 1 in row.abnormal


def test_no_benchmark_means_no_abnormal_columns():
    stock = build_stock()
    stock.add_earnings(EarningsReport.from_iso("2023-01-03", 1.2, 1.0))
    drift = analyze_drift(stock, horizons=(1,))
    assert not any(c.startswith("abn_") for c in drift.columns)


def test_run_up_measures_the_move_into_the_announcement():
    frame = prices([100.0, 105.0, 110.0, 121.0], start="2023-01-02")
    # Sessions are 01-02, 01-03, 01-04, 01-05; the event lands on the last.
    report = EarningsReport.from_iso("2023-01-05", 1.2, 1.0)
    row = drift_for_event(frame, report, horizons=(), pre_window=2)
    # Announcement close 121 against 105 two sessions earlier.
    assert row.run_up == pytest.approx(121 / 105 - 1)


def test_run_up_is_none_without_enough_prior_history():
    frame = prices([100.0, 110.0], start="2023-01-02")
    report = EarningsReport.from_iso("2023-01-02", 1.2, 1.0)
    row = drift_for_event(frame, report, horizons=(1,), pre_window=5)
    assert row.run_up is None


# --------------------------------------------------------------------------- #
# Pooling and cross-sectional tests
# --------------------------------------------------------------------------- #


def synthetic_drift(n: int, effect: float, seed: int = 0) -> pd.DataFrame:
    """Events whose 5-day abnormal return is `effect` x surprise plus noise."""
    rng = np.random.default_rng(seed)
    surprise = rng.normal(0, 10, n)
    noise = rng.normal(0, 0.02, n)
    return pd.DataFrame(
        {
            "event_date": pd.bdate_range("2020-01-01", periods=n),
            "surprise_pct": surprise,
            "abn_5d": effect * surprise / 100 + noise,
        }
    )


def test_pool_stacks_frames_and_sorts_by_date():
    a = synthetic_drift(10, 0.0, seed=1)
    b = synthetic_drift(10, 0.0, seed=2)
    pooled = pool([a, b])
    assert len(pooled) == 20
    assert pooled["event_date"].is_monotonic_increasing


def test_pool_ignores_empty_frames():
    assert len(pool([synthetic_drift(5, 0.0), pd.DataFrame()])) == 5


def test_pool_of_nothing_is_empty():
    assert pool([]).empty


def test_buckets_are_ordered_by_surprise():
    buckets = surprise_buckets(synthetic_drift(200, 0.3), horizon=5)
    assert len(buckets) == 5
    surprises = [b.mean_surprise for b in buckets]
    assert surprises == sorted(surprises)


def test_buckets_detect_a_real_effect():
    """With a genuine relationship, drift should rise across the groups."""
    buckets = surprise_buckets(synthetic_drift(400, 0.5, seed=7), horizon=5)
    assert buckets[-1].mean_return > buckets[0].mean_return
    spread = spread_test(synthetic_drift(400, 0.5, seed=7), horizon=5)
    assert spread.spread > 0
    assert spread.significant
    assert spread.monotonic


def test_buckets_report_no_effect_when_there_is_none():
    """The important case: the test must fail to find what is not there."""
    frame = synthetic_drift(400, 0.0, seed=11)
    spread = spread_test(frame, horizon=5)
    assert spread is not None
    assert not spread.significant


def test_buckets_need_enough_events_per_group():
    assert surprise_buckets(synthetic_drift(8, 0.5), horizon=5) == []


def test_buckets_return_nothing_for_a_missing_horizon():
    assert surprise_buckets(synthetic_drift(200, 0.5), horizon=99) == []


def test_hit_rate_is_near_a_half_with_no_effect():
    rate = hit_rate(synthetic_drift(600, 0.0, seed=3), horizon=5)
    assert 0.4 < rate < 0.6


def test_hit_rate_is_high_with_a_strong_effect():
    rate = hit_rate(synthetic_drift(600, 3.0, seed=3), horizon=5)
    assert rate > 0.8


def test_hit_rate_ignores_zero_surprises():
    frame = synthetic_drift(50, 1.0)
    frame.loc[:10, "surprise_pct"] = 0.0
    assert hit_rate(frame, horizon=5) is not None


def test_report_states_when_the_effect_is_absent():
    text = format_summary(synthetic_drift(400, 0.0, seed=5), horizons=(1, 5, 10))
    assert "does not hold up" in text or "Not distinguishable" in text
