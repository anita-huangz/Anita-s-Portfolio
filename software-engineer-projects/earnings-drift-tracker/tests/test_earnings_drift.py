"""Tests for the drift arithmetic and the parsing around it."""

from __future__ import annotations

from datetime import date

import pandas as pd
import pytest

from earnings_drift import EarningsReport, Stock, analyze_drift, drift_for_event
from earnings_drift.drift import summarize, surprise_correlation
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

    drift = analyze_drift(stock, horizons=(1, 5))
    assert len(drift) == 2
    assert list(drift.columns) == [
        "event_date", "baseline_date", "surprise_pct", "1d", "5d"
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
    assert "Average post-earnings drift" in text
    assert "correlation" in text.lower()
