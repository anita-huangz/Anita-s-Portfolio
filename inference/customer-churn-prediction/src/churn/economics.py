"""Turning a probability into a decision.

A churn model does not retain anybody. Someone has to be offered something,
that offer costs money, and most of the people who accept it were never going
to leave. The model is only useful if it makes that trade better than a coin
flip, and "AUC 0.85" does not say whether it does.

Two things live here.

**A threshold chosen by expected value, not by F1.** F1 balances precision
against recall as if the two errors cost the same. They do not: contacting a
happy customer costs one discount, losing an unhappy one costs their whole
remaining value. The optimal cut-off falls out of those numbers and is nowhere
near 0.5.

**Value that depends on how long they would have stayed.** This is where the
survival model earns its place. Saving a $20/month customer with eight months
left is not the same deal as saving a $100/month customer with four years
left, and a classifier cannot tell them apart -- "will churn" is the same
label for both. Expected remaining lifetime comes from the survival curve, so
the two halves of the project meet here.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

#: Share of targeted customers who accept a retention offer and stay. The
#: literature puts telecom save rates in the 20-40% range; it is an assumption
#: either way, and `Campaign.sensitivity` exists because of that.
DEFAULT_ACCEPTANCE = 0.30

#: Gross margin retained per dollar of revenue.
DEFAULT_MARGIN = 0.30

#: Larger than any probability, so `p >= threshold` selects nobody.
_ABOVE_ANY_PROBABILITY = 1.0 + 1e-9


@dataclass(frozen=True)
class Campaign:
    """What an intervention costs and what it is worth.

    Every number here is an assumption about the business, not something the
    data can settle. They are arguments rather than constants so that the
    conclusion can be stress-tested instead of asserted.
    """

    #: Cost of making the offer to one customer: the discount, plus the call.
    offer_cost: float = 30.0
    #: Probability a targeted churner accepts and stays.
    acceptance: float = DEFAULT_ACCEPTANCE
    #: Fraction of revenue that is margin.
    margin: float = DEFAULT_MARGIN
    #: How far ahead to count value.
    horizon_months: float = 24.0

    def __post_init__(self) -> None:
        if not 0 <= self.acceptance <= 1:
            raise ValueError("acceptance must be a probability")
        if self.offer_cost < 0:
            raise ValueError("offer_cost cannot be negative")


@dataclass(frozen=True)
class ThresholdResult:
    threshold: float
    targeted: int
    expected_value: float
    true_positives: int
    false_positives: int

    @property
    def value_per_customer(self) -> float:
        return self.expected_value / max(self.targeted, 1)

    @property
    def targets_nobody(self) -> bool:
        """Running no campaign, which is a decision and sometimes the right one."""
        return self.targeted == 0


def customer_value(
    monthly_charges: np.ndarray,
    expected_months: np.ndarray,
    campaign: Campaign,
) -> np.ndarray:
    """Margin at stake for each customer over the horizon.

    `expected_months` is what the survival curve contributes: the area under
    S(t) for that customer, capped at the horizon. Using a constant instead --
    the implicit assumption when you only have a classifier -- values every
    saved customer identically.
    """
    monthly = np.asarray(monthly_charges, dtype=float)
    months = np.clip(np.asarray(expected_months, dtype=float), 0, campaign.horizon_months)
    return monthly * months * campaign.margin


def expected_value_curve(
    probability: np.ndarray,
    churned: np.ndarray,
    value: np.ndarray,
    campaign: Campaign,
    thresholds: np.ndarray | None = None,
) -> list[ThresholdResult]:
    """Net value of targeting everyone above each threshold.

    For a targeted customer the offer always costs `offer_cost`. It only
    returns anything when they were going to leave *and* they accept, which is
    `acceptance` of the time -- so a false positive is a pure loss and a true
    positive pays `acceptance x value`.
    """
    probability = np.asarray(probability, dtype=float)
    churned = np.asarray(churned).astype(bool)
    value = np.asarray(value, dtype=float)
    if thresholds is None:
        # The last entry sits above every possible probability, so "target
        # nobody" is on the menu. Without it the optimiser is forced to run
        # *some* campaign, and when the offer costs more than a customer is
        # worth the best it can report is the least-bad way to lose money.
        thresholds = np.append(np.linspace(0.02, 0.98, 97), _ABOVE_ANY_PROBABILITY)

    results = []
    for t in thresholds:
        targeted = probability >= t
        n = int(targeted.sum())
        saved = targeted & churned
        gain = campaign.acceptance * value[saved].sum()
        cost = campaign.offer_cost * n
        results.append(
            ThresholdResult(
                threshold=float(t),
                targeted=n,
                expected_value=float(gain - cost),
                true_positives=int(saved.sum()),
                false_positives=int((targeted & ~churned).sum()),
            )
        )
    return results


def best_threshold(curve: list[ThresholdResult]) -> ThresholdResult:
    """The threshold that maximises expected value.

    Ties break toward the higher threshold: contacting fewer people for the
    same money is the better campaign, and it leaves budget elsewhere.
    """
    if not curve:
        raise ValueError("empty curve")
    return max(curve, key=lambda r: (r.expected_value, r.threshold))


def expected_months_remaining(
    survival: np.ndarray, times: np.ndarray, horizon: float
) -> np.ndarray:
    """Area under each customer's survival curve, out to the horizon.

    `survival` is `(n_customers, n_times)`. The integral of S(t) is expected
    time-to-event -- restricted to the horizon because the curve beyond the
    observation window is extrapolation, not evidence.
    """
    survival = np.atleast_2d(np.asarray(survival, dtype=float))
    times = np.asarray(times, dtype=float)
    keep = times <= horizon
    grid = np.concatenate(([0.0], times[keep], [horizon]))
    values = np.concatenate(
        (np.ones((survival.shape[0], 1)), survival[:, keep]), axis=1
    )
    return values @ np.diff(grid)


def targeting_comparison(
    probability: np.ndarray,
    churned: np.ndarray,
    value: np.ndarray,
    campaign: Campaign,
    budget: int,
) -> dict[str, float]:
    """Who to call when you can only call `budget` people.

    Three policies, same budget. Ranking by probability is the standard
    answer and is not the best one: it spends the budget on whoever is most
    likely to leave regardless of whether they were worth keeping. Ranking by
    *expected value* -- probability times what they are worth -- is the
    decision the model should be supporting.
    """
    probability = np.asarray(probability, dtype=float)
    churned = np.asarray(churned).astype(bool)
    value = np.asarray(value, dtype=float)
    budget = min(budget, len(probability))

    def net(selected: np.ndarray) -> float:
        saved = selected & churned
        return float(
            campaign.acceptance * value[saved].sum() - campaign.offer_cost * selected.sum()
        )

    def top(scores: np.ndarray) -> np.ndarray:
        chosen = np.zeros(len(scores), dtype=bool)
        chosen[np.argsort(-scores)[:budget]] = True
        return chosen

    rng = np.random.default_rng(0)
    random_pick = np.zeros(len(probability), dtype=bool)
    random_pick[rng.choice(len(probability), budget, replace=False)] = True

    return {
        "by_probability": net(top(probability)),
        "by_expected_value": net(top(probability * value)),
        "random": net(random_pick),
        "everyone": net(np.ones(len(probability), dtype=bool)),
        "nobody": 0.0,
    }
