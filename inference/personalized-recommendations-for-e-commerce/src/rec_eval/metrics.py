"""Ranking metrics, because a recommender produces a list and not a label.

Accuracy, precision and AUC all ask "was this item right". A recommender is
judged on *where* the right item landed: an item ranked 2nd is nearly as good
as 1st and an item ranked 400th is useless, and no classification metric knows
the difference.

All four metrics here are cut-off based, because that is how recommendations
are consumed -- nobody scrolls to position 200.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


def recall_at_k(ranked: list[str], relevant: set[str], k: int) -> float:
    """Share of the relevant items that made the top k.

    The headline number for a recommender, and the one that depends most on k:
    recall@20 out of 24 possible items is nearly free, which is why the cut-off
    has to be reported next to it.
    """
    if not relevant:
        return float("nan")
    hits = len(set(ranked[:k]) & relevant)
    return hits / min(len(relevant), k)


def precision_at_k(ranked: list[str], relevant: set[str], k: int) -> float:
    if k == 0:
        return float("nan")
    return len(set(ranked[:k]) & relevant) / k


def average_precision(ranked: list[str], relevant: set[str], k: int) -> float:
    """Precision at each hit, averaged. Rewards putting hits early."""
    if not relevant:
        return float("nan")
    hits, total = 0, 0.0
    for position, item in enumerate(ranked[:k], start=1):
        if item in relevant:
            hits += 1
            total += hits / position
    return total / min(len(relevant), k)


def reciprocal_rank(ranked: list[str], relevant: set[str]) -> float:
    """1 / rank of the first hit. 0 if there is none.

    The right metric when the user only wants one thing and will take the
    first acceptable option.
    """
    for position, item in enumerate(ranked, start=1):
        if item in relevant:
            return 1.0 / position
    return 0.0


def ndcg_at_k(ranked: list[str], relevant: set[str], k: int) -> float:
    """Discounted cumulative gain, normalised by the best possible ordering.

    The discount is logarithmic, so moving an item from 10th to 5th matters
    less than moving it from 2nd to 1st -- which is the right shape, because
    attention falls off that way too.
    """
    if not relevant:
        return float("nan")
    gains = [1.0 if item in relevant else 0.0 for item in ranked[:k]]
    discount = 1.0 / np.log2(np.arange(2, len(gains) + 2))
    actual = float(np.sum(np.array(gains) * discount))
    best_count = min(len(relevant), k)
    ideal = float(np.sum(discount[:best_count]))
    return actual / ideal if ideal > 0 else float("nan")


@dataclass(frozen=True)
class RankingScores:
    """Metrics averaged over customers, with the sample size attached."""

    name: str
    k: int
    customers: int
    recall: float
    precision: float
    map_score: float
    mrr: float
    ndcg: float

    def row(self) -> str:
        return (
            f"{self.name:<22}{self.recall:>10.4f}{self.precision:>11.4f}"
            f"{self.map_score:>10.4f}{self.mrr:>8.4f}{self.ndcg:>9.4f}"
        )


def score_rankings(
    name: str,
    rankings: list[tuple[list[str], set[str]]],
    k: int = 5,
) -> RankingScores:
    """Average every metric over a list of (ranked items, held-out truth)."""
    if not rankings:
        raise ValueError("no rankings to score")
    recalls, precisions, maps, rrs, ndcgs = [], [], [], [], []
    for ranked, relevant in rankings:
        recalls.append(recall_at_k(ranked, relevant, k))
        precisions.append(precision_at_k(ranked, relevant, k))
        maps.append(average_precision(ranked, relevant, k))
        rrs.append(reciprocal_rank(ranked, relevant))
        ndcgs.append(ndcg_at_k(ranked, relevant, k))
    return RankingScores(
        name=name,
        k=k,
        customers=len(rankings),
        recall=float(np.nanmean(recalls)),
        precision=float(np.nanmean(precisions)),
        map_score=float(np.nanmean(maps)),
        mrr=float(np.nanmean(rrs)),
        ndcg=float(np.nanmean(ndcgs)),
    )
