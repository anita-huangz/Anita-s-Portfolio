"""Load the incidents, and encode them once for everything downstream."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.preprocessing import OneHotEncoder, StandardScaler

DATA = (
    Path(__file__).resolve().parents[2]
    / "data"
    / "Global_Cybersecurity_Threats_2015-2024.csv"
)

NUMERIC = [
    "Financial Loss (in Million $)",
    "Number of Affected Users",
    "Incident Resolution Time (in Hours)",
]
CATEGORICAL = [
    "Country",
    "Attack Type",
    "Target Industry",
    "Attack Source",
    "Security Vulnerability Type",
    "Defense Mechanism Used",
]


class SchemaError(ValueError):
    """The file is not the dataset this package expects."""


@dataclass(frozen=True)
class Incidents:
    frame: pd.DataFrame

    def __len__(self) -> int:
        return len(self.frame)

    @property
    def numeric(self) -> pd.DataFrame:
        return self.frame[NUMERIC].astype(float)

    @property
    def categorical(self) -> pd.DataFrame:
        return self.frame[CATEGORICAL]

    def encoded(self) -> np.ndarray:
        """Standardised numerics plus one-hot categoricals.

        The single design matrix every method here sees, so that "the
        clustering disagreed with the projection" can never be an artefact of
        two different encodings.
        """
        transformer = ColumnTransformer(
            [
                ("numeric", StandardScaler(), NUMERIC),
                # Dense, because silhouette and the gap statistic both need
                # Euclidean distances over the whole matrix; a sparse result
                # would not convert.
                (
                    "categorical",
                    OneHotEncoder(handle_unknown="ignore", sparse_output=False),
                    CATEGORICAL,
                ),
            ]
        )
        return np.asarray(transformer.fit_transform(self.frame), dtype=float)


def load(path: Path | str = DATA) -> Incidents:
    frame = pd.read_csv(path)
    missing = {*NUMERIC, *CATEGORICAL} - set(frame.columns)
    if missing:
        raise SchemaError(f"missing column(s): {sorted(missing)}")
    return Incidents(frame=frame)


def shuffle_within_columns(
    frame: pd.DataFrame, seed: int = 0
) -> pd.DataFrame:
    """Shuffle every column independently.

    The right null for "is there structure here". It keeps each column's
    marginal distribution exactly -- same values, same counts -- and destroys
    every relationship between columns. Anything a method still finds
    afterwards is a property of the shapes, not of the data.

    Compare with sampling from a uniform box, which also changes the
    marginals and so confounds "no joint structure" with "different spread".
    """
    rng = np.random.default_rng(seed)
    shuffled = {column: rng.permutation(values.to_numpy())
                for column, values in frame.items()}
    return pd.DataFrame(shuffled, index=frame.index)
