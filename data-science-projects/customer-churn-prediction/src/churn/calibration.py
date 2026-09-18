"""Is a predicted 70% actually 70%?

Ranking and calibration are different properties and a model can have one
without the other. AUC only asks whether churners score above non-churners; it
is unchanged if you square every probability. But the moment a number is
multiplied by a dollar value -- which is exactly what the expected-value
threshold does -- the magnitude has to mean something.

`class_weight="balanced"` and SMOTE both make this worse on purpose: they
rebalance the classes so the model stops predicting the majority, and the
probabilities that come out are shifted away from the real base rate as a
direct consequence. A model trained that way ranks fine and prices badly.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class Reliability:
    """Predicted probability against observed frequency, in bins."""

    bin_centre: np.ndarray
    predicted: np.ndarray
    observed: np.ndarray
    count: np.ndarray

    @property
    def max_gap(self) -> float:
        return float(np.max(np.abs(self.predicted - self.observed)))


def reliability_curve(
    probability: np.ndarray, label: np.ndarray, bins: int = 10
) -> Reliability:
    """Group predictions into bins and compare each bin's mean to its outcome.

    Equal-width bins, so an empty bin stays empty rather than being quietly
    merged -- a model that never predicts above 0.8 should look like one.
    """
    probability = np.asarray(probability, dtype=float)
    label = np.asarray(label).astype(float)
    edges = np.linspace(0, 1, bins + 1)
    idx = np.clip(np.digitize(probability, edges[1:-1]), 0, bins - 1)

    centre, predicted, observed, count = [], [], [], []
    for b in range(bins):
        mask = idx == b
        centre.append((edges[b] + edges[b + 1]) / 2)
        count.append(int(mask.sum()))
        predicted.append(float(probability[mask].mean()) if mask.any() else np.nan)
        observed.append(float(label[mask].mean()) if mask.any() else np.nan)
    return Reliability(
        bin_centre=np.array(centre),
        predicted=np.array(predicted),
        observed=np.array(observed),
        count=np.array(count),
    )


def brier_score(probability: np.ndarray, label: np.ndarray) -> float:
    """Mean squared error of the probabilities. Lower is better.

    Unlike AUC this is a *proper* scoring rule: it is minimised only by
    reporting your true belief, so it punishes a model that ranks well while
    being systematically over-confident.
    """
    probability = np.asarray(probability, dtype=float)
    label = np.asarray(label).astype(float)
    return float(np.mean((probability - label) ** 2))


def expected_calibration_error(
    probability: np.ndarray, label: np.ndarray, bins: int = 10
) -> float:
    """Average gap between predicted and observed, weighted by bin size."""
    curve = reliability_curve(probability, label, bins=bins)
    filled = curve.count > 0
    weights = curve.count[filled] / curve.count.sum()
    gaps = np.abs(curve.predicted[filled] - curve.observed[filled])
    return float(np.sum(weights * gaps))


def brier_skill_score(probability: np.ndarray, label: np.ndarray) -> float:
    """Brier score against the one you would get by always predicting the base rate.

    0 means the model is no better than quoting the overall churn rate to
    everybody; 1 is perfect. The raw Brier score looks reassuringly small on
    any imbalanced problem, which is what this corrects for.
    """
    label = np.asarray(label).astype(float)
    baseline = np.full_like(label, label.mean(), dtype=float)
    return float(1 - brier_score(probability, label) / brier_score(baseline, label))
