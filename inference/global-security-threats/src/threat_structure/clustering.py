"""Clustering, judged against a null instead of against a picture.

K-Means returns k clusters for any input. Given 3,000 points of independent
uniform noise it returns k contiguous slabs, they look clean, and the
silhouette score is positive. So a positive silhouette is not evidence of
clusters; it is evidence that k-means ran.

Three ways to tell the difference, none of which need ground truth:

**Compare against a null.** Shuffle every column independently -- keeping each
marginal exactly, destroying every joint relationship -- and re-cluster. If the
silhouette is the same, what was found was geometry.

**Check stability.** Resample the rows and re-cluster. Real clusters survive
resampling and the assignments agree (high adjusted Rand index between runs);
arbitrary partitions of a cloud do not.

**Use the gap statistic.** Compares within-cluster dispersion against what a
uniform reference of the same shape produces, which is exactly the right
comparison, and unlike silhouette it can return k = 1.

The third is the one that answers the original question, because silhouette
and elbow plots have no way to say "there are no clusters here".
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from sklearn.cluster import KMeans
from sklearn.metrics import adjusted_rand_score, silhouette_score

from .data import Incidents, shuffle_within_columns

RANDOM_STATE = 42


def fit_kmeans(matrix: np.ndarray, k: int, seed: int = RANDOM_STATE) -> np.ndarray:
    return KMeans(n_clusters=k, n_init=10, random_state=seed).fit_predict(matrix)


@dataclass(frozen=True)
class NullComparison:
    """Silhouette on the real data against the same on shuffled columns."""

    k: int
    observed: float
    null_scores: np.ndarray

    @property
    def null_mean(self) -> float:
        return float(self.null_scores.mean())

    @property
    def null_std(self) -> float:
        return float(self.null_scores.std(ddof=1))

    @property
    def z_score(self) -> float:
        return (
            (self.observed - self.null_mean) / self.null_std
            if self.null_std > 0
            else 0.0
        )

    @property
    def p_value(self) -> float:
        hits = int((self.null_scores >= self.observed).sum())
        return (hits + 1) / (len(self.null_scores) + 1)

    @property
    def smallest_possible_p(self) -> float:
        """The p-value you get when *no* draw beats the observation.

        `1 / (draws + 1)`. It matters because it puts a floor on significance:
        with 10 draws the smallest reachable p-value is 0.091, so the test
        cannot return a significant result however large the effect. That is a
        property of the number of draws, not of the data, and it is the sort
        of thing that gets read as "no effect".
        """
        return 1.0 / (len(self.null_scores) + 1)

    @property
    def can_reach_significance(self) -> bool:
        """Were there enough draws for a significant result to be possible?"""
        return self.smallest_possible_p < 0.05

    @property
    def better_than_noise(self) -> bool:
        return self.p_value < 0.05


def compare_with_null(
    data: Incidents, k: int = 4, draws: int = 30, seed: int = RANDOM_STATE
) -> NullComparison:
    """Cluster the data, then cluster shuffled versions of it.

    The shuffle preserves every column's marginal distribution, so the null
    has the same shapes and scales as the real thing and differs only in
    whether the columns relate to each other.
    """
    if draws < 19:
        raise ValueError(
            f"{draws} draws puts a floor of {1 / (draws + 1):.3f} on the "
            "p-value, so a significant result is unreachable; use at least 19"
        )
    matrix = data.encoded()
    observed = float(silhouette_score(matrix, fit_kmeans(matrix, k, seed)))

    scores = np.empty(draws)
    for i in range(draws):
        shuffled = Incidents(frame=shuffle_within_columns(data.frame, seed=seed + i))
        null_matrix = shuffled.encoded()
        scores[i] = silhouette_score(null_matrix, fit_kmeans(null_matrix, k, seed))
    return NullComparison(k=k, observed=observed, null_scores=scores)


@dataclass(frozen=True)
class Stability:
    """How much the cluster assignments survive resampling."""

    k: int
    scores: np.ndarray

    @property
    def mean_ari(self) -> float:
        return float(self.scores.mean())

    @property
    def interval(self) -> tuple[float, float]:
        return tuple(np.quantile(self.scores, [0.05, 0.95]))

    @property
    def stable(self) -> bool:
        """0.75 is the usual threshold for calling a clustering reproducible.

        Below about 0.5 the partition is essentially redrawn each time, which
        means the boundaries are a property of the sample and not of any
        structure.
        """
        return self.mean_ari > 0.75


def stability(
    data: Incidents, k: int = 4, draws: int = 25, seed: int = RANDOM_STATE
) -> Stability:
    """Bootstrap the rows, re-cluster, and compare assignments on the overlap.

    Comparing *on the overlap* is what makes this meaningful: two runs on
    different samples can only be compared where they share rows.
    """
    matrix = data.encoded()
    rng = np.random.default_rng(seed)
    n = len(matrix)
    scores = np.empty(draws)
    for i in range(draws):
        first = rng.choice(n, n, replace=True)
        second = rng.choice(n, n, replace=True)
        shared = np.intersect1d(first, second)
        labels_a = fit_kmeans(matrix[first], k, seed)
        labels_b = fit_kmeans(matrix[second], k, seed)
        # Map each shared row back to its label in both runs.
        first_position = {row: pos for pos, row in enumerate(first)}
        second_position = {row: pos for pos, row in enumerate(second)}
        a = np.array([labels_a[first_position[row]] for row in shared])
        b = np.array([labels_b[second_position[row]] for row in shared])
        scores[i] = adjusted_rand_score(a, b)
    return Stability(k=k, scores=scores)


@dataclass(frozen=True)
class GapStatistic:
    """Gap for each k, and the smallest k the criterion supports."""

    frame: pd.DataFrame

    @property
    def best_k(self) -> int:
        """Tibshirani's rule: the smallest k whose gap clears the next one's error bar.

        This can return 1, which is the whole reason for using it. Silhouette
        and elbow plots are undefined at k = 1 and so structurally incapable
        of reporting "there are no clusters".
        """
        gaps = self.frame["gap"].to_numpy()
        errors = self.frame["s_k"].to_numpy()
        ks = self.frame.index.to_numpy()
        for i in range(len(ks) - 1):
            if gaps[i] >= gaps[i + 1] - errors[i + 1]:
                return int(ks[i])
        return int(ks[-1])

    @property
    def says_no_clusters(self) -> bool:
        return self.best_k == 1


def _dispersion(matrix: np.ndarray, labels: np.ndarray) -> float:
    """Pooled within-cluster sum of squared distances to the centroid."""
    total = 0.0
    for label in np.unique(labels):
        points = matrix[labels == label]
        if len(points) < 2:
            continue
        centre = points.mean(axis=0)
        total += float(((points - centre) ** 2).sum())
    return total


def gap_statistic(
    data: Incidents,
    max_k: int = 6,
    references: int = 10,
    seed: int = RANDOM_STATE,
) -> GapStatistic:
    """Within-cluster dispersion against a uniform reference of the same extent.

    The reference is drawn uniformly inside the bounding box of the data, which
    is the standard construction. For data that really is uniform noise the
    real dispersion matches the reference at every k, the gap never rises, and
    the rule returns k = 1.
    """
    matrix = data.encoded()
    rng = np.random.default_rng(seed)
    low, high = matrix.min(axis=0), matrix.max(axis=0)

    rows = {}
    for k in range(1, max_k + 1):
        labels = fit_kmeans(matrix, k, seed) if k > 1 else np.zeros(len(matrix), int)
        observed = np.log(max(_dispersion(matrix, labels), 1e-12))

        reference_logs = np.empty(references)
        for r in range(references):
            sample = rng.uniform(low, high, size=matrix.shape)
            ref_labels = (
                fit_kmeans(sample, k, seed) if k > 1 else np.zeros(len(sample), int)
            )
            reference_logs[r] = np.log(max(_dispersion(sample, ref_labels), 1e-12))

        rows[k] = {
            "gap": float(reference_logs.mean() - observed),
            "s_k": float(
                reference_logs.std(ddof=1) * np.sqrt(1 + 1 / references)
            ),
        }
    return GapStatistic(frame=pd.DataFrame(rows).T)
