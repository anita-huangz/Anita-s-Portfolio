"""Point-in-time backtest of cross-sectional equity factor strategies."""

from .factors import (
    Factor,
    LowVolatilityFactor,
    MomentumFactor,
    SizeFactor,
    ValueFactor,
    get_factors,
    score_universe,
    zscore,
)
from .metrics import max_drawdown, performance_metrics
from .optimizer import RankBasedOptimizer
from .portfolio import Portfolio, Security
from .simulation import BacktestResult, point_in_time_exposures, run_backtest

__all__ = [
    "BacktestResult",
    "Factor",
    "LowVolatilityFactor",
    "MomentumFactor",
    "Portfolio",
    "RankBasedOptimizer",
    "Security",
    "SizeFactor",
    "ValueFactor",
    "get_factors",
    "max_drawdown",
    "performance_metrics",
    "point_in_time_exposures",
    "run_backtest",
    "score_universe",
    "zscore",
]

__version__ = "0.2.0"
