"""Do the outlier detectors agree with each other?

With no ground truth there is no way to check whether a flagged incident is
really unusual, so the notebook's Isolation Forest and Local Outlier Factor
results had nothing to be graded against. But they can be graded against
*each other*: two methods looking at the same real anomalies should largely
agree, and two methods carving arbitrary edges off a uniform cloud should
agree about as often as chance.

That comparison needs the right chance baseline. Two detectors each flagging
5% of 3,000 rows overlap on 7.5 rows on average by coincidence, so raw overlap
looks impressively non-zero and means nothing. The adjusted version below
divides by it.

**And then the result has to be read carefully.** On this dataset the two
detectors agree four times more than chance -- which looks like corroboration
and is not. They agree because they share a geometric notion of "far from the
middle", and in a 39-column one-hot space the far-from-the-middle points are
the rows with rare *combinations* of categories. On independent uniform
columns, rare combinations occur at random. Two methods agreeing is evidence
that they are the same kind of method, not evidence that what they found is
real; `tail_checks` exists to ask what they actually picked.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from sklearn.ensemble import IsolationForest
from sklearn.neighbors import LocalOutlierFactor

from .data import Incidents

RANDOM_STATE = 42
CONTAMINATION = 0.05


def isolation_forest_flags(
    matrix: np.ndarray, contamination: float = CONTAMINATION, seed: int = RANDOM_STATE
) -> np.ndarray:
    model = IsolationForest(
        n_estimators=200, contamination=contamination, random_state=seed
    )
    return model.fit_predict(matrix) == -1


def local_outlier_flags(
    matrix: np.ndarray, contamination: float = CONTAMINATION, neighbours: int = 20
) -> np.ndarray:
    model = LocalOutlierFactor(n_neighbors=neighbours, contamination=contamination)
    return model.fit_predict(matrix) == -1


@dataclass(frozen=True)
class Agreement:
    """How much two detectors overlap, against how much chance would give."""

    n: int
    flagged_a: int
    flagged_b: int
    overlap: int

    @property
    def expected_overlap(self) -> float:
        """Overlap from two independent detectors flagging the same counts."""
        return self.flagged_a * self.flagged_b / self.n

    @property
    def jaccard(self) -> float:
        union = self.flagged_a + self.flagged_b - self.overlap
        return self.overlap / union if union else 0.0

    @property
    def excess(self) -> float:
        """Observed overlap divided by the chance expectation.

        1.0 means the two detectors agree exactly as often as two unrelated
        ones would. This is the number to read, not the raw overlap, which is
        never zero and so always looks like agreement.
        """
        expected = self.expected_overlap
        return self.overlap / expected if expected > 0 else float("inf")

    @property
    def agree(self) -> bool:
        """Materially more overlap than chance.

        Note what this does and does not establish. Agreement between two
        detectors is not validation: both are ranking distance from the centre
        of the same cloud, so they will agree on uniform noise too. It rules
        out one of them being broken; it says nothing about whether the
        flagged rows are anomalous in any sense that matters.
        """
        return self.excess > 2.0


def detector_agreement(
    data: Incidents, contamination: float = CONTAMINATION, seed: int = RANDOM_STATE
) -> Agreement:
    """Run both detectors on the same matrix and compare what they flag."""
    matrix = data.encoded()
    first = isolation_forest_flags(matrix, contamination, seed)
    second = local_outlier_flags(matrix, contamination)
    return Agreement(
        n=len(matrix),
        flagged_a=int(first.sum()),
        flagged_b=int(second.sum()),
        overlap=int((first & second).sum()),
    )


@dataclass(frozen=True)
class TailCheck:
    """Is a 'multivariate anomaly' just the tail of one column?"""

    column: str
    flagged_mean_percentile: float

    @property
    def is_just_a_tail(self) -> bool:
        """Flagged rows sit far out on a single variable.

        If so, the multivariate machinery added nothing a `sort` would not
        have found -- which is worth knowing before describing the result as
        anomaly detection.
        """
        return abs(self.flagged_mean_percentile - 0.5) > 0.2


def tail_checks(
    data: Incidents, contamination: float = CONTAMINATION, seed: int = RANDOM_STATE
) -> list[TailCheck]:
    """For each numeric column, where do the flagged rows sit in its distribution?"""
    from .data import NUMERIC

    matrix = data.encoded()
    flagged = isolation_forest_flags(matrix, contamination, seed)
    checks = []
    for column in NUMERIC:
        values = data.frame[column].to_numpy(dtype=float)
        ranks = values.argsort().argsort() / (len(values) - 1)
        checks.append(
            TailCheck(
                column=column,
                flagged_mean_percentile=float(ranks[flagged].mean()),
            )
        )
    return checks
