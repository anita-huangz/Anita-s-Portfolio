"""Turning scores into weights."""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


@dataclass(frozen=True)
class RankBasedOptimizer:
    """Select the top N by score and weight them.

    Weighting is by *rank*, not by score value. Score-proportional weighting --
    `weight = score / sum(scores)` -- breaks whenever scores can be negative,
    which they always can here: z-scores are centred on zero, and factors like
    size are negative by construction. A negative denominator flips every sign
    and produces short positions in a long-only book, or a near-zero denominator
    produces enormous weights.
    """

    top_n: int = 3
    #: "equal" gives 1/N; "rank" weights N, N-1, ... 1 normalised.
    scheme: str = "equal"

    def __post_init__(self) -> None:
        if self.top_n < 1:
            raise ValueError("top_n must be at least 1")
        if self.scheme not in {"equal", "rank"}:
            raise ValueError(f"unknown scheme: {self.scheme!r}")

    def optimize(self, scores: pd.Series) -> dict[str, float]:
        usable = pd.to_numeric(scores, errors="coerce").dropna()
        if usable.empty:
            return {}

        # Sort by score, then ticker, so ties resolve identically on every run.
        ordered = usable.sort_index().sort_values(ascending=False, kind="stable")
        selected = ordered.head(self.top_n)
        count = len(selected)

        if self.scheme == "equal":
            return {ticker: 1.0 / count for ticker in selected.index}

        ranks = range(count, 0, -1)
        denominator = count * (count + 1) / 2
        return {
            ticker: rank / denominator
            for ticker, rank in zip(selected.index, ranks, strict=True)
        }
