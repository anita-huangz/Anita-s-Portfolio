"""Warming rates, and honest error bars around them."""

from .data import DataError, Series, load
from .trend import (
    Autocorrelation,
    Trend,
    block_bootstrap,
    mann_kendall,
    newey_west,
    ordinary_least_squares,
    residual_autocorrelation,
)

__all__ = [
    "Autocorrelation",
    "DataError",
    "Series",
    "Trend",
    "block_bootstrap",
    "load",
    "mann_kendall",
    "newey_west",
    "ordinary_least_squares",
    "residual_autocorrelation",
]
