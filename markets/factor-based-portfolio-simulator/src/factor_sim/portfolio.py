"""Holdings, rebalancing, and valuation."""

from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd


@dataclass
class Portfolio:
    """A long-only book of whole-dollar positions.

    Cash is tracked explicitly rather than assumed to be zero after a
    rebalance: with transaction costs, or weights that do not sum to one, a
    residual exists and pretending otherwise quietly fabricates or destroys
    value.
    """

    cash: float
    holdings: dict[str, float] = field(default_factory=dict)
    #: Basis points charged on the notional traded at each rebalance.
    cost_bps: float = 0.0

    def value(self, prices: dict[str, float]) -> float:
        held = sum(
            prices[ticker] * shares
            for ticker, shares in self.holdings.items()
            if ticker in prices
        )
        return self.cash + held

    def rebalance(self, weights: dict[str, float], prices: dict[str, float]) -> float:
        """Move to target weights. Returns the transaction cost charged.

        Weights are taken as fractions of total portfolio value; whatever is
        not allocated stays in cash.
        """
        total = self.value(prices)
        if total <= 0:
            return 0.0

        targets = {
            ticker: (weight * total) / prices[ticker]
            for ticker, weight in weights.items()
            if prices.get(ticker, 0) > 0
        }

        traded_notional = 0.0
        for ticker in set(targets) | set(self.holdings):
            price = prices.get(ticker)
            if price is None:
                continue
            delta = targets.get(ticker, 0.0) - self.holdings.get(ticker, 0.0)
            traded_notional += abs(delta) * price

        cost = traded_notional * (self.cost_bps / 10_000.0)
        self.holdings = {t: s for t, s in targets.items() if s > 0}
        self.cash = total - sum(
            prices[t] * s for t, s in self.holdings.items()
        ) - cost
        return cost


@dataclass(frozen=True)
class Security:
    """One name: its price history and its factor exposures over time."""

    ticker: str
    prices: pd.Series

    def price_on(self, day: pd.Timestamp) -> float | None:
        try:
            value = float(self.prices.loc[day])
        except (KeyError, TypeError, ValueError):
            return None
        return None if pd.isna(value) else value
