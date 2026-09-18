"""Leave-one-out evaluation, the standard protocol for a recommender.

For each customer, hide one purchased subcategory, rank everything from what
is left, and see where the hidden item landed. Averaged over customers, that
is an estimate of how the recommender behaves on the next purchase.

Two details that decide whether the number means anything:

**The held-out item must be removed from the visible history.** Leaving it in
makes every recommender look perfect, and it is a one-character mistake.

**Customers with a single purchase cannot be evaluated.** Hold out their only
item and there is no history to rank from. A third of these customers are in
that position, so they are excluded and the count is reported rather than the
sample quietly shrinking.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .data import Catalogue, Customers
from .metrics import RankingScores, score_rankings
from .recommenders import Context, Recommender


@dataclass(frozen=True)
class Evaluation:
    scores: list[RankingScores]
    evaluated: int
    excluded: int

    def best(self) -> RankingScores:
        return max(self.scores, key=lambda s: s.ndcg)

    def named(self, name: str) -> RankingScores:
        return next(s for s in self.scores if s.name == name)


def leave_one_out(
    customers: Customers,
    catalogue: Catalogue,
    recommenders: dict[str, Recommender],
    k: int = 5,
    seed: int = 0,
) -> Evaluation:
    """Score every recommender on the same held-out items.

    The same held-out item per customer for all recommenders, so the
    comparison is paired -- otherwise a lucky draw for one of them is
    indistinguishable from a real difference.
    """
    rng = np.random.default_rng(seed)
    usable = customers.with_enough_history

    problems: list[tuple[int, list[str], set[str]]] = []
    for index in usable:
        items = list(dict.fromkeys(customers.purchases[index]))
        held = items[rng.integers(0, len(items))]
        visible = [i for i in items if i != held]
        problems.append((index, visible, {held}))

    results = []
    for name, recommend in recommenders.items():
        rankings = []
        for index, visible, truth in problems:
            context = Context(visible=visible, browsing=customers.browsing[index])
            rankings.append((recommend(context, catalogue), truth))
        results.append(score_rankings(name, rankings, k=k))

    return Evaluation(
        scores=results,
        evaluated=len(problems),
        excluded=len(customers) - len(problems),
    )
