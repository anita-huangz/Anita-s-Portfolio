"""Does this dataset have any structure? Tested against a null before clustering."""

from .anomalies import (
    Agreement,
    TailCheck,
    detector_agreement,
    isolation_forest_flags,
    local_outlier_flags,
    tail_checks,
)
from .clustering import (
    GapStatistic,
    NullComparison,
    Stability,
    compare_with_null,
    fit_kmeans,
    gap_statistic,
    stability,
)
from .data import Incidents, SchemaError, load, shuffle_within_columns
from .structure import (
    AssociationTest,
    BalanceTest,
    UniformityTest,
    associations,
    balance,
    cramers_v,
    uniformity,
)

__all__ = [
    "Agreement",
    "AssociationTest",
    "BalanceTest",
    "GapStatistic",
    "Incidents",
    "NullComparison",
    "SchemaError",
    "Stability",
    "TailCheck",
    "UniformityTest",
    "associations",
    "balance",
    "compare_with_null",
    "cramers_v",
    "detector_agreement",
    "fit_kmeans",
    "gap_statistic",
    "isolation_forest_flags",
    "load",
    "local_outlier_flags",
    "shuffle_within_columns",
    "stability",
    "tail_checks",
    "uniformity",
]
