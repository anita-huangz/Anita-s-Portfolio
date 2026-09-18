"""Trend estimation and, mostly, the uncertainty around it.

The slope is easy and every method here agrees on it. The error bar is the
part that is easy to get wrong, so most of these tests are about intervals --
checked against statsmodels where an independent implementation exists, and
against synthetic series with known properties where it does not.
"""

from __future__ import annotations

import numpy as np
import pytest
import statsmodels.api as sm

from climate_trend.data import DataError, Series, load
from climate_trend.trend import (
    block_bootstrap,
    mann_kendall,
    newey_west,
    ordinary_least_squares,
    residual_autocorrelation,
)


@pytest.fixture(scope="module")
def cities():
    return load()


def synthetic(slope=0.2, rho=0.0, n=75, sigma=0.5, seed=0) -> Series:
    """A series with a known slope and a known amount of persistence."""
    rng = np.random.default_rng(seed)
    noise = np.zeros(n)
    for t in range(1, n):
        noise[t] = rho * noise[t - 1] + rng.normal(0, sigma)
    year = np.arange(1950, 1950 + n, dtype=float)
    decades = (year - year.mean()) / 10.0
    return Series(
        city="synthetic", latitude=0.0, year=year,
        temperature=10.0 + slope * decades + noise,
    )


# --------------------------------------------------------------------------- #
# Data
# --------------------------------------------------------------------------- #


def test_six_cities_of_annual_means_load(cities):
    assert len(cities) == 6
    for series in cities.values():
        assert len(series) == 75
        assert series.span == (1950, 2024)


def test_duplicate_years_are_rejected(tmp_path):
    path = tmp_path / "bad.csv"
    path.write_text("city,year,latitude,mean_c\nX,2000,0,1\nX,2000,0,2\n")
    with pytest.raises(DataError, match="duplicate years"):
        load(path)


def test_a_missing_column_is_caught(tmp_path):
    path = tmp_path / "bad.csv"
    path.write_text("city,year\nX,2000\n")
    with pytest.raises(DataError, match="missing column"):
        load(path)


def test_year_is_expressed_in_centred_decades(cities):
    """So the slope is degrees per decade without a later rescaling step."""
    decades = cities["London"].decades
    assert decades.mean() == pytest.approx(0.0, abs=1e-12)
    assert decades.max() - decades.min() == pytest.approx(7.4)


# --------------------------------------------------------------------------- #
# The slope, which everything agrees on
# --------------------------------------------------------------------------- #


def test_ols_matches_statsmodels(cities):
    series = cities["London"]
    mine = ordinary_least_squares(series)
    theirs = sm.OLS(
        series.temperature, sm.add_constant(series.decades)
    ).fit()
    assert mine.slope == pytest.approx(theirs.params[1], abs=1e-10)
    assert mine.standard_error == pytest.approx(theirs.bse[1], abs=1e-10)
    assert mine.p_value == pytest.approx(theirs.pvalues[1], abs=1e-10)


def test_newey_west_matches_statsmodels(cities):
    series = cities["London"]
    mine = newey_west(series, lag=3)
    theirs = sm.OLS(series.temperature, sm.add_constant(series.decades)).fit(
        cov_type="HAC", cov_kwds={"maxlags": 3, "use_correction": False}
    )
    assert mine.standard_error == pytest.approx(theirs.bse[1], rel=1e-8)


def test_every_method_recovers_a_planted_slope():
    series = synthetic(slope=0.35, rho=0.4, seed=1)
    for trend in (
        ordinary_least_squares(series),
        newey_west(series),
        block_bootstrap(series, draws=400),
        mann_kendall(series),
    ):
        assert trend.slope == pytest.approx(0.35, abs=0.12), trend.method


def test_a_flat_series_produces_no_significant_trend():
    series = synthetic(slope=0.0, rho=0.3, seed=2)
    assert not newey_west(series).significant
    assert not mann_kendall(series).significant


# --------------------------------------------------------------------------- #
# The error bar, which they do not
# --------------------------------------------------------------------------- #


def test_the_residuals_are_autocorrelated(cities):
    """Which is the assumption OLS needs and temperature violates."""
    for name in ("London", "Sydney", "Reykjavik"):
        result = residual_autocorrelation(cities[name])
        assert result.lag1 > 0.15, name
        assert result.is_correlated, name
        assert result.effective_sample_size < result.n


def test_the_effective_sample_is_smaller_than_the_nominal_one(cities):
    """Reykjavik's 75 years are worth about 35 independent ones."""
    result = residual_autocorrelation(cities["Reykjavik"])
    assert result.effective_sample_size < 45
    assert result.inflation > 1.3


def test_correcting_for_autocorrelation_widens_the_interval(cities):
    """It can only widen it when residuals are positively autocorrelated."""
    for name in ("London", "Sydney", "Reykjavik"):
        naive = ordinary_least_squares(cities[name])
        corrected = newey_west(cities[name])
        assert corrected.standard_error > naive.standard_error, name
        assert corrected.width > naive.width, name


def test_the_bootstrap_agrees_with_newey_west(cities):
    """Two corrections that share no assumptions, landing in the same place."""
    for name in ("London", "Sydney"):
        hac = newey_west(cities[name])
        boot = block_bootstrap(cities[name], draws=1200)
        assert boot.standard_error == pytest.approx(hac.standard_error, rel=0.35)


def test_the_bootstrap_brackets_the_point_estimate(cities):
    """The bug this guards against.

    The first version resampled the *temperatures* against a fixed time axis,
    which scrambles the trend out of the series: the interval came back as
    [-0.11, +0.11] around a point estimate of +0.235. That is a null
    distribution, not a sampling distribution. Residuals are what gets
    resampled.
    """
    for name in ("London", "Sydney", "Reykjavik"):
        result = block_bootstrap(cities[name], draws=800)
        assert result.low < result.slope < result.high, name
        assert result.low > 0, name


def test_independent_noise_needs_no_correction():
    """With rho = 0 the corrected and naive intervals should nearly agree.

    Otherwise the correction is not a correction, it is a penalty.
    """
    series = synthetic(slope=0.2, rho=0.0, n=200, seed=3)
    naive = ordinary_least_squares(series)
    corrected = newey_west(series)
    assert corrected.standard_error == pytest.approx(
        naive.standard_error, rel=0.25
    )


def test_more_persistence_means_a_wider_interval():
    quiet = newey_west(synthetic(slope=0.2, rho=0.0, seed=4))
    sticky = newey_west(synthetic(slope=0.2, rho=0.7, seed=4))
    assert sticky.standard_error > quiet.standard_error


def test_a_block_longer_than_the_series_is_refused(cities):
    with pytest.raises(ValueError, match="shorter than the series"):
        block_bootstrap(cities["London"], block=100)


# --------------------------------------------------------------------------- #
# Mann-Kendall
# --------------------------------------------------------------------------- #


def test_sens_slope_shrugs_off_an_outlier():
    """The median of pairwise slopes barely moves; least squares does."""
    series = synthetic(slope=0.2, rho=0.0, seed=5)
    spiked = Series(
        city="spiked", latitude=0.0, year=series.year,
        temperature=series.temperature.copy(),
    )
    spiked.temperature[10] += 25.0  # one absurd year

    ols_shift = abs(
        ordinary_least_squares(spiked).slope - ordinary_least_squares(series).slope
    )
    sen_shift = abs(mann_kendall(spiked).slope - mann_kendall(series).slope)
    assert sen_shift < ols_shift / 3


def test_mann_kendall_detects_a_monotone_trend_without_assuming_a_shape():
    n = 75
    year = np.arange(1950, 1950 + n, dtype=float)
    # Strictly increasing but wildly non-linear.
    series = Series(
        city="curved", latitude=0.0, year=year,
        temperature=np.exp(np.linspace(0, 3, n)),
    )
    assert mann_kendall(series).significant
    assert mann_kendall(series).slope > 0


def test_every_city_is_warming(cities):
    """The finding, by a test that assumes nothing about the distribution."""
    for name, series in cities.items():
        result = mann_kendall(series)
        assert result.slope > 0, name
        assert result.significant, name


def test_the_year_to_year_wobble_can_exceed_a_decade_of_trend(cities):
    """Which is why nobody notices a trend by remembering last summer."""
    for name, series in cities.items():
        trend = newey_west(series).slope
        assert series.year_to_year_sd > trend, name
