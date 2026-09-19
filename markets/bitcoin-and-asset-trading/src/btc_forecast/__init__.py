"""Forecasting BTC, evaluated against a one-line baseline that beats it."""

from .backtest import BacktestResult, backtest_signal, buy_and_hold
from .baselines import all_baselines, ar_returns, drift, ewma, naive
from .data import DataError, Prices, build_daily_from_minutes, load
from .leakage import LeakComparison, ScalerLeak, measure_scaler_leak, minmax_scale
from .metrics import (
    Accuracy,
    DieboldMariano,
    diebold_mariano,
    directional_accuracy,
    mae,
    mape,
    return_r2,
    rmse,
)
from .walkforward import (
    Fold,
    FoldResult,
    WalkForwardResult,
    rolling_origin,
    walk_forward,
)

__all__ = [
    "Accuracy",
    "BacktestResult",
    "DataError",
    "DieboldMariano",
    "Fold",
    "FoldResult",
    "LeakComparison",
    "Prices",
    "ScalerLeak",
    "WalkForwardResult",
    "all_baselines",
    "ar_returns",
    "backtest_signal",
    "build_daily_from_minutes",
    "buy_and_hold",
    "diebold_mariano",
    "directional_accuracy",
    "drift",
    "ewma",
    "load",
    "mae",
    "mape",
    "measure_scaler_leak",
    "minmax_scale",
    "naive",
    "return_r2",
    "rmse",
    "rolling_origin",
    "walk_forward",
]
