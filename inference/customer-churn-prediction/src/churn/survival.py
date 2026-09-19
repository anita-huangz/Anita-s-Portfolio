"""Survival analysis: Kaplan-Meier, the log-rank test, and Cox regression.

Written from scratch rather than imported, because the point of the project is
the reasoning and the arithmetic is checkable. `tests/test_survival.py` checks
every estimator here against statsmodels' independent implementations, so
"from scratch" does not mean "on trust".

Why survival analysis at all: 73.5% of these customers had not left when the
data was cut. Their lifetime is not 24 months, it is *at least* 24 months, and
the difference is the whole problem. Dropping them throws away three quarters
of the data; treating their tenure as a final answer pulls every estimate
downward. Censoring is what these estimators are for.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field

import numpy as np
import pandas as pd
from scipy import stats

#: Newton-Raphson stops when the largest coefficient step falls below this.
TOLERANCE = 1e-9
MAX_ITERATIONS = 100


# --------------------------------------------------------------------------- #
# Kaplan-Meier
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class KaplanMeier:
    """The survival curve, and how confident we are in it.

    `S(t)` is the probability of still being a customer at `t` months. It is a
    product over the event times of "given you made it this far, you survived
    this month too" — which is how censored customers keep contributing: they
    sit in the at-risk denominator for every month they were observed and then
    leave the calculation without ever counting as a failure.
    """

    times: np.ndarray
    survival: np.ndarray
    at_risk: np.ndarray
    events: np.ndarray
    #: Greenwood standard error of S(t).
    standard_error: np.ndarray

    def predict(self, t: float | np.ndarray) -> np.ndarray:
        """S(t) as a right-continuous step function."""
        t = np.atleast_1d(np.asarray(t, dtype=float))
        # No events at all -- every observation censored -- means the curve
        # never leaves 1. Guarded before indexing because `np.where` evaluates
        # both branches, so the "safe" branch still indexes an empty array.
        if self.times.size == 0:
            return np.ones_like(t)
        idx = np.searchsorted(self.times, t, side="right") - 1
        return np.where(idx < 0, 1.0, self.survival[np.clip(idx, 0, None)])

    def confidence_interval(self, alpha: float = 0.05) -> tuple[np.ndarray, np.ndarray]:
        """Pointwise CI on the log-log scale, so it cannot escape [0, 1].

        A plain S ± 1.96·SE interval routinely runs above 1 or below 0 in the
        tails, which is visibly wrong on a probability.
        """
        z = stats.norm.ppf(1 - alpha / 2)
        with np.errstate(divide="ignore", invalid="ignore"):
            log_s = np.log(self.survival)
            # SE of log(-log S) by the delta method.
            se_loglog = self.standard_error / np.abs(self.survival * log_s)
            spread = z * se_loglog
            lower = self.survival ** np.exp(spread)
            upper = self.survival ** np.exp(-spread)
        return np.clip(lower, 0, 1), np.clip(upper, 0, 1)

    @property
    def median_survival(self) -> float:
        """First time S(t) <= 0.5, or inf if the curve never gets there.

        `inf` is the honest answer, not a bug: if most customers are still
        subscribed at the end of the window, the median lifetime has not
        happened yet and no amount of arithmetic will produce it.
        """
        reached = np.flatnonzero(self.survival <= 0.5)
        return float(self.times[reached[0]]) if reached.size else float("inf")

    def restricted_mean(self, horizon: float) -> float:
        """Area under S(t) up to `horizon` — expected months retained.

        The usable summary when the median is undefined: "how much subscriber
        time do we expect in the next three years" is answerable even when
        "when will half of them leave" is not.
        """
        grid = np.concatenate(([0.0], self.times[self.times <= horizon], [horizon]))
        # `grid` can hold a duplicate when an event lands exactly on the
        # horizon; the zero-width interval contributes nothing either way.
        values = self.predict(grid[:-1])
        return float(np.sum(values * np.diff(grid)))


def kaplan_meier(duration: np.ndarray, event: np.ndarray) -> KaplanMeier:
    """Non-parametric survival curve from right-censored observations."""
    duration = np.asarray(duration, dtype=float)
    event = np.asarray(event).astype(int)
    if duration.shape != event.shape:
        raise ValueError("duration and event must be the same length")
    if duration.size == 0:
        raise ValueError("no observations")

    times = np.unique(duration[event == 1])
    n_at_risk = np.array([(duration >= t).sum() for t in times], dtype=float)
    n_events = np.array([((duration == t) & (event == 1)).sum() for t in times], dtype=float)

    survival = np.cumprod(1.0 - n_events / n_at_risk)
    # Greenwood's formula for the variance of the product.
    with np.errstate(divide="ignore", invalid="ignore"):
        terms = n_events / (n_at_risk * (n_at_risk - n_events))
    cumulative = np.cumsum(np.nan_to_num(terms, posinf=0.0))
    standard_error = survival * np.sqrt(cumulative)

    return KaplanMeier(
        times=times,
        survival=survival,
        at_risk=n_at_risk,
        events=n_events,
        standard_error=standard_error,
    )


@dataclass(frozen=True)
class LogRankResult:
    statistic: float
    p_value: float
    degrees_of_freedom: int

    @property
    def significant(self) -> bool:
        return self.p_value < 0.05


def log_rank_test(
    duration: np.ndarray, event: np.ndarray, group: np.ndarray
) -> LogRankResult:
    """Do these groups have the same survival curve?

    Compares observed events against what each group would contribute if the
    hazard were shared, pooled over every event time. Unlike comparing churn
    *rates*, it accounts for the fact that groups are observed for different
    lengths of time -- which here they very much are.
    """
    duration = np.asarray(duration, dtype=float)
    event = np.asarray(event).astype(int)
    group = np.asarray(group)
    labels = np.unique(group)
    if labels.size < 2:
        raise ValueError("need at least two groups")

    times = np.unique(duration[event == 1])
    k = labels.size
    observed = np.zeros(k)
    expected = np.zeros(k)
    variance = np.zeros((k, k))

    for t in times:
        at_risk = np.array([((group == g) & (duration >= t)).sum() for g in labels], float)
        events = np.array(
            [((group == g) & (duration == t) & (event == 1)).sum() for g in labels], float
        )
        n, d = at_risk.sum(), events.sum()
        if n <= 1 or d == 0:
            continue
        share = at_risk / n
        observed += events
        expected += d * share
        # Multivariate hypergeometric covariance at this event time.
        factor = d * (n - d) / (n - 1)
        variance += factor * (np.diag(share) - np.outer(share, share))

    # One group is redundant: the counts sum to the total, so the covariance
    # matrix is singular. Drop the last and test the remaining k-1.
    diff = (observed - expected)[:-1]
    cov = variance[:-1, :-1]
    statistic = float(diff @ np.linalg.pinv(cov) @ diff)
    dof = k - 1
    return LogRankResult(
        statistic=statistic,
        p_value=float(stats.chi2.sf(statistic, dof)),
        degrees_of_freedom=dof,
    )


# --------------------------------------------------------------------------- #
# Cox proportional hazards
# --------------------------------------------------------------------------- #


@dataclass
class CoxModel:
    """Cox proportional hazards, fitted by Newton-Raphson on the partial likelihood.

    The model says each customer's hazard is a shared baseline shaped by time,
    multiplied by `exp(x·beta)` — a constant factor that does not depend on
    when you look. So a coefficient reads as a *hazard ratio*: `exp(beta) =
    1.5` means 50% more likely to leave in any given month, all else equal.

    The baseline never has to be estimated to get the coefficients, which is
    the trick that makes this work: the partial likelihood conditions on the
    set of customers still at risk at each event time, and the baseline
    cancels out of the ratio.
    """

    names: list[str]
    coefficients: np.ndarray
    #: Inverse of the observed information, i.e. the covariance of beta.
    covariance: np.ndarray
    log_likelihood: float
    iterations: int
    converged: bool
    #: Breslow baseline cumulative hazard, evaluated at the event times.
    baseline_times: np.ndarray = field(default_factory=lambda: np.array([]))
    baseline_cumulative_hazard: np.ndarray = field(default_factory=lambda: np.array([]))
    means: np.ndarray = field(default_factory=lambda: np.array([]))

    @property
    def hazard_ratios(self) -> np.ndarray:
        return np.exp(self.coefficients)

    @property
    def standard_errors(self) -> np.ndarray:
        return np.sqrt(np.diag(self.covariance))

    @property
    def z_scores(self) -> np.ndarray:
        return self.coefficients / self.standard_errors

    @property
    def p_values(self) -> np.ndarray:
        return 2 * stats.norm.sf(np.abs(self.z_scores))

    def summary(self) -> pd.DataFrame:
        frame = pd.DataFrame(
            {
                "coef": self.coefficients,
                "hazard_ratio": self.hazard_ratios,
                "std_err": self.standard_errors,
                "z": self.z_scores,
                "p": self.p_values,
            },
            index=self.names,
        )
        z = stats.norm.ppf(0.975)
        frame["hr_lower"] = np.exp(self.coefficients - z * self.standard_errors)
        frame["hr_upper"] = np.exp(self.coefficients + z * self.standard_errors)
        return frame.sort_values("p")

    def risk_score(self, X: np.ndarray | pd.DataFrame) -> np.ndarray:
        """`x·beta` — the log hazard ratio against the average customer."""
        values = np.asarray(X, dtype=float)
        centred = values - self.means if self.means.size else values
        return centred @ self.coefficients

    def predict_survival(
        self, X: np.ndarray | pd.DataFrame, times: np.ndarray
    ) -> np.ndarray:
        """S(t | x) for each row, as `(n_rows, n_times)`.

        `S(t|x) = S0(t) ** exp(x·beta)`: the same baseline curve, raised to a
        power. That single shape for everyone *is* the proportional-hazards
        assumption, and `proportional_hazards_test` checks whether it holds.
        """
        if self.baseline_times.size == 0:
            raise ValueError("no baseline hazard; fit with the training data first")
        scores = np.exp(self.risk_score(X))
        idx = np.clip(np.searchsorted(self.baseline_times, times, side="right") - 1, 0, None)
        cumulative = np.where(
            np.asarray(times) < self.baseline_times[0],
            0.0,
            self.baseline_cumulative_hazard[idx],
        )
        return np.exp(-np.outer(scores, cumulative))


def _efron_terms(
    X: np.ndarray, beta: np.ndarray, duration: np.ndarray, event: np.ndarray
) -> tuple[float, np.ndarray, np.ndarray]:
    """Log partial likelihood, gradient, and Hessian, with Efron's tie handling.

    Tenure here is whole months, so ties are not an edge case: hundreds of
    customers share an event time. Breslow's simpler approximation biases
    coefficients toward zero exactly when ties are heavy, so Efron's is worth
    the extra bookkeeping -- it averages over the orderings the tied events
    could have had instead of pretending they happened at once.
    """
    n, p = X.shape
    scores = np.exp(X @ beta)
    loglik = 0.0
    gradient = np.zeros(p)
    hessian = np.zeros((p, p))

    order = np.argsort(-duration)  # descending, so the risk set only grows
    sorted_t = duration[order]
    sorted_e = event[order]
    sorted_X = X[order]
    sorted_s = scores[order]

    risk_sum = 0.0
    risk_x = np.zeros(p)
    risk_xx = np.zeros((p, p))

    i = 0
    while i < n:
        t = sorted_t[i]
        # Everyone with this exact time enters the risk set together.
        j = i
        tied_sum = 0.0
        tied_x = np.zeros(p)
        tied_xx = np.zeros((p, p))
        tied_count = 0
        while j < n and sorted_t[j] == t:
            s, x = sorted_s[j], sorted_X[j]
            risk_sum += s
            risk_x += s * x
            risk_xx += s * np.outer(x, x)
            if sorted_e[j] == 1:
                tied_count += 1
                loglik += x @ beta
                gradient += x
                tied_sum += s
                tied_x += s * x
                tied_xx += s * np.outer(x, x)
            j += 1

        for m in range(tied_count):
            share = m / tied_count
            denom = risk_sum - share * tied_sum
            num_x = risk_x - share * tied_x
            num_xx = risk_xx - share * tied_xx
            ratio = num_x / denom
            loglik -= np.log(denom)
            gradient -= ratio
            hessian -= num_xx / denom - np.outer(ratio, ratio)
        i = j

    return float(loglik), gradient, hessian


def fit_cox(
    X: pd.DataFrame | np.ndarray,
    duration: np.ndarray,
    event: np.ndarray,
    names: list[str] | None = None,
) -> CoxModel:
    """Fit Cox regression by Newton-Raphson."""
    if isinstance(X, pd.DataFrame):
        names = names or list(X.columns)
        values = X.to_numpy(dtype=float)
    else:
        values = np.asarray(X, dtype=float)
        names = names or [f"x{i}" for i in range(values.shape[1])]

    duration = np.asarray(duration, dtype=float)
    event = np.asarray(event).astype(int)
    if event.sum() == 0:
        raise ValueError("no events; the partial likelihood is empty")
    if values.shape[0] != duration.size:
        raise ValueError("X and duration disagree on the number of rows")

    rank = np.linalg.matrix_rank(values)
    if rank < values.shape[1]:
        raise ValueError(
            f"design matrix has {values.shape[1]} columns but rank {rank}: "
            f"{values.shape[1] - rank} are linear combinations of the others, "
            "so their coefficients are not identified. Look for categories "
            "that restate another column."
        )

    beta = np.zeros(values.shape[1])
    converged = False
    iterations = 0
    while iterations < MAX_ITERATIONS:
        iterations += 1
        _, gradient, hessian = _efron_terms(values, beta, duration, event)
        step = np.linalg.solve(hessian, gradient)
        beta = beta - step
        if np.max(np.abs(step)) < TOLERANCE:
            converged = True
            break

    loglik, _, hessian = _efron_terms(values, beta, duration, event)
    covariance = np.linalg.inv(-hessian)

    model = CoxModel(
        names=list(names),
        coefficients=beta,
        covariance=covariance,
        log_likelihood=loglik,
        iterations=iterations,
        converged=converged,
        means=values.mean(axis=0),
    )
    model.baseline_times, model.baseline_cumulative_hazard = _breslow_baseline(
        values, beta, duration, event, model.means
    )
    return model



@dataclass
class StratifiedCoxModel(CoxModel):
    """Cox with a separate baseline hazard per stratum.

    The ordinary model assumes a covariate's effect is a constant multiplier on
    the hazard for the whole follow-up. On this data that assumption fails for
    16 of 20 covariates, which `proportional_hazards_test` reports and which
    makes every hazard ratio a time-average over a changing effect.

    Stratifying is the standard response, and the trick is what it gives up.
    The offending variable is moved *out* of the linear predictor and into the
    baseline: each stratum gets its own baseline hazard, free to have any shape
    at all, so the variable no longer has to act proportionally. In exchange
    you no longer get a coefficient for it -- there is nothing to estimate,
    because its whole effect is absorbed into the baselines.

    That is the right trade for a nuisance variable whose effect you need to
    control for but do not need to quantify. It is the wrong trade if the
    variable is the thing you are studying, which is why `stratify_on` is a
    choice rather than something applied automatically to whatever fails.

    The likelihood decomposes cleanly: each stratum contributes its own Efron
    terms over its own risk sets, and the total is the sum. Only the
    coefficients are shared.
    """

    #: Column the baseline is split on, and the value for each stratum.
    stratum_name: str = ""
    strata: list[str] = field(default_factory=list)
    stratum_sizes: dict[str, int] = field(default_factory=dict)
    #: Per-stratum Breslow baselines, keyed by stratum label.
    baselines: dict[str, tuple[np.ndarray, np.ndarray]] = field(default_factory=dict)

    def predict_survival(
        self, X: pd.DataFrame | np.ndarray, t: np.ndarray, strata: Sequence[str]
    ) -> np.ndarray:
        """Survival curves, each row using its own stratum's baseline."""
        values = X.to_numpy(dtype=float) if isinstance(X, pd.DataFrame) else np.asarray(
            X, dtype=float
        )
        scores = np.exp((values - self.means) @ self.coefficients)
        t = np.asarray(t, dtype=float)
        out = np.empty((len(values), len(t)))
        for row, (score, stratum) in enumerate(zip(scores, strata, strict=True)):
            times, cumulative = self.baselines[stratum]
            if times.size == 0:
                out[row] = 1.0
                continue
            idx = np.searchsorted(times, t, side="right") - 1
            hazard = np.where(idx < 0, 0.0, cumulative[np.clip(idx, 0, None)])
            out[row] = np.exp(-score * hazard)
        return out


def fit_stratified_cox(
    X: pd.DataFrame,
    duration: np.ndarray,
    event: np.ndarray,
    strata: Sequence[str],
    stratum_name: str = "stratum",
) -> StratifiedCoxModel:
    """Fit Cox with one baseline hazard per stratum, sharing the coefficients.

    `strata` is one label per row. Columns belonging to the stratifying
    variable must already be out of `X`; leaving them in is not an error the
    maths catches, it just estimates a coefficient for something the baseline
    has already absorbed.
    """
    names = list(X.columns)
    values = X.to_numpy(dtype=float)
    duration = np.asarray(duration, dtype=float)
    event = np.asarray(event).astype(int)
    labels = np.asarray(strata)

    if labels.size != values.shape[0]:
        raise ValueError("strata and X disagree on the number of rows")
    if event.sum() == 0:
        raise ValueError("no events; the partial likelihood is empty")

    groups = {}
    for label in dict.fromkeys(labels.tolist()):
        mask = labels == label
        if event[mask].sum() == 0:
            # A stratum with no events contributes nothing to the partial
            # likelihood; including it would divide by an empty risk set.
            continue
        groups[str(label)] = mask
    if not groups:
        raise ValueError("no stratum contains an event")

    rank = np.linalg.matrix_rank(values)
    if rank < values.shape[1]:
        raise ValueError(
            f"design matrix has {values.shape[1]} columns but rank {rank}; "
            "check that the stratifying variable's columns were removed"
        )

    def terms(beta: np.ndarray) -> tuple[float, np.ndarray, np.ndarray]:
        """Efron terms summed over strata, each with its own risk sets."""
        total_ll = 0.0
        total_g = np.zeros(values.shape[1])
        total_h = np.zeros((values.shape[1], values.shape[1]))
        for mask in groups.values():
            ll, g, h = _efron_terms(values[mask], beta, duration[mask], event[mask])
            total_ll += ll
            total_g += g
            total_h += h
        return total_ll, total_g, total_h

    beta = np.zeros(values.shape[1])
    converged = False
    iterations = 0
    while iterations < MAX_ITERATIONS:
        iterations += 1
        _, gradient, hessian = terms(beta)
        step = np.linalg.solve(hessian, gradient)
        beta = beta - step
        if np.max(np.abs(step)) < TOLERANCE:
            converged = True
            break

    loglik, _, hessian = terms(beta)
    means = values.mean(axis=0)
    model = StratifiedCoxModel(
        names=names,
        coefficients=beta,
        covariance=np.linalg.inv(-hessian),
        log_likelihood=loglik,
        iterations=iterations,
        converged=converged,
        means=means,
        stratum_name=stratum_name,
        strata=sorted(groups),
        stratum_sizes={label: int(mask.sum()) for label, mask in groups.items()},
    )
    for label, mask in groups.items():
        model.baselines[label] = _breslow_baseline(
            values[mask], beta, duration[mask], event[mask], means
        )
    return model


def stratified_proportional_hazards_test(
    model: StratifiedCoxModel,
    X: pd.DataFrame,
    duration: np.ndarray,
    event: np.ndarray,
    strata: Sequence[str],
) -> ProportionalHazardsTest:
    """Re-run the Schoenfeld test, with residuals computed within strata.

    The point of stratifying is to remove one variable's time-varying effect
    from the linear predictor. Whether that helped is a question the same test
    answers -- run again, properly, with each residual measured against the
    risk set of its own stratum.
    """
    values = X.to_numpy(dtype=float)
    duration = np.asarray(duration, dtype=float)
    event = np.asarray(event).astype(int)
    labels = np.asarray(strata)
    scores = np.exp(values @ model.coefficients)

    residuals, event_times = [], []
    for label in dict.fromkeys(labels.tolist()):
        mask = labels == label
        d, e, v, sc = duration[mask], event[mask], values[mask], scores[mask]
        for t in np.unique(d[e == 1]):
            at_risk = d >= t
            weights = sc[at_risk]
            expected = (weights[:, None] * v[at_risk]).sum(axis=0) / weights.sum()
            for row in v[(d == t) & (e == 1)]:
                residuals.append(row - expected)
                event_times.append(t)

    matrix = np.asarray(residuals)
    ranked = stats.rankdata(np.asarray(event_times, dtype=float))
    corr, pvals = {}, {}
    for j, name in enumerate(model.names):
        column = matrix[:, j]
        if np.allclose(column, column[0]):
            corr[name], pvals[name] = 0.0, 1.0
            continue
        r, p = stats.pearsonr(ranked, column)
        corr[name], pvals[name] = float(r), float(p)
    return ProportionalHazardsTest(
        correlations=pd.Series(corr), p_values=pd.Series(pvals)
    )


@dataclass(frozen=True)
class PeriodComparison:
    """The same model fitted early and late, to see what actually changed.

    A proportional-hazards test says an effect is not constant. It does not say
    how it moves, and a p-value on a Schoenfeld residual is not something to
    put in front of anyone. Splitting the follow-up and fitting both halves
    answers the question directly: here is the hazard ratio in the first year,
    here it is afterwards.

    The early fit uses every customer with their follow-up censored at the
    cut-off, not only those who left early -- restricting to them would
    condition on the outcome and bias every coefficient.
    """

    cutoff: float
    early: CoxModel
    late: CoxModel
    names: list[str]
    early_events: int
    late_events: int

    def table(self) -> pd.DataFrame:
        """Hazard ratios side by side, ordered by how much they moved."""
        frame = pd.DataFrame(
            {
                "early": self.early.hazard_ratios,
                "late": self.late.hazard_ratios,
            },
            index=self.names,
        )
        frame["ratio"] = frame["late"] / frame["early"]
        # A sign flip is the interesting case: protective early, risky later.
        frame["reverses"] = (frame["early"] < 1) != (frame["late"] < 1)
        return frame.sort_values("ratio", ascending=False)

    @property
    def reversals(self) -> list[str]:
        """Covariates whose effect changes direction across the cut-off."""
        table = self.table()
        return sorted(table.index[table["reverses"]])


def compare_periods(
    X: pd.DataFrame,
    duration: np.ndarray,
    event: np.ndarray,
    cutoff: float,
) -> PeriodComparison:
    """Fit the same covariates before and after `cutoff` months."""
    duration = np.asarray(duration, dtype=float)
    event = np.asarray(event).astype(int)

    # Everyone contributes to the early fit, censored at the cut-off. Keeping
    # only customers who churned early would select on the outcome.
    early_event = np.where(duration <= cutoff, event, 0)
    early = fit_cox(X, np.minimum(duration, cutoff), early_event)

    survived = duration > cutoff
    if event[survived].sum() == 0:
        raise ValueError(f"no events after month {cutoff:g}")
    late = fit_cox(X[survived], duration[survived], event[survived])

    return PeriodComparison(
        cutoff=float(cutoff),
        early=early,
        late=late,
        names=list(X.columns),
        early_events=int(early_event.sum()),
        late_events=int(event[survived].sum()),
    )

def _breslow_baseline(
    X: np.ndarray,
    beta: np.ndarray,
    duration: np.ndarray,
    event: np.ndarray,
    means: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    """Cumulative baseline hazard, centred on the mean covariate vector.

    Centring matters: without it the "baseline" is a customer whose every
    feature is zero, which for these columns is nobody at all.
    """
    scores = np.exp((X - means) @ beta)
    times = np.unique(duration[event == 1])
    increments = []
    for t in times:
        at_risk = duration >= t
        d = int(((duration == t) & (event == 1)).sum())
        increments.append(d / scores[at_risk].sum())
    return times, np.cumsum(increments)


def concordance_index(
    risk: np.ndarray, duration: np.ndarray, event: np.ndarray
) -> float:
    """Harrell's C: of the pairs we can order, how many did the model rank right?

    The survival analogue of AUC, and it handles censoring properly. A pair is
    only comparable when we know who failed first — comparing two customers
    who were both still subscribed tells us nothing, so those pairs are
    excluded rather than guessed at.
    """
    risk = np.asarray(risk, dtype=float)
    duration = np.asarray(duration, dtype=float)
    event = np.asarray(event).astype(int)

    concordant = tied = comparable = 0.0
    for i in np.flatnonzero(event == 1):
        # i failed at duration[i]; anyone observed beyond that outlived them.
        later = duration > duration[i]
        if not later.any():
            continue
        comparable += later.sum()
        concordant += (risk[later] < risk[i]).sum()
        tied += (risk[later] == risk[i]).sum()

    if comparable == 0:
        return float("nan")
    return float((concordant + 0.5 * tied) / comparable)


@dataclass(frozen=True)
class ProportionalHazardsTest:
    """Does the hazard ratio really stay constant over time?"""

    correlations: pd.Series
    p_values: pd.Series

    @property
    def violations(self) -> list[str]:
        return sorted(self.p_values[self.p_values < 0.05].index)

    @property
    def holds(self) -> bool:
        return not self.violations


def proportional_hazards_test(
    model: CoxModel,
    X: pd.DataFrame,
    duration: np.ndarray,
    event: np.ndarray,
) -> ProportionalHazardsTest:
    """Correlate the scaled Schoenfeld residuals with time.

    The whole model rests on one assumption: a covariate's effect is a
    constant multiplier on the hazard, the same in month 2 as in month 60. If
    a residual trends with time, that is false for that covariate and its
    single coefficient is an average over a changing effect.

    Reported rather than hidden, because on this data it does not hold, and a
    hazard ratio quoted from a model whose assumption fails is a number with
    an asterisk on it.
    """
    values = X.to_numpy(dtype=float)
    duration = np.asarray(duration, dtype=float)
    event = np.asarray(event).astype(int)
    scores = np.exp(values @ model.coefficients)

    residuals, event_times = [], []
    for t in np.unique(duration[event == 1]):
        at_risk = duration >= t
        weights = scores[at_risk]
        expected = (weights[:, None] * values[at_risk]).sum(axis=0) / weights.sum()
        for row in values[(duration == t) & (event == 1)]:
            residuals.append(row - expected)
            event_times.append(t)

    matrix = np.asarray(residuals)
    times = np.asarray(event_times, dtype=float)
    # Rank-transform time: the test should not be driven by the long tail of
    # tenures, only by whether the residuals drift in order.
    ranked = stats.rankdata(times)

    corr, pvals = {}, {}
    for j, name in enumerate(model.names):
        column = matrix[:, j]
        if np.allclose(column, column[0]):
            corr[name], pvals[name] = 0.0, 1.0
            continue
        r, p = stats.pearsonr(ranked, column)
        corr[name], pvals[name] = float(r), float(p)
    return ProportionalHazardsTest(
        correlations=pd.Series(corr), p_values=pd.Series(pvals)
    )
