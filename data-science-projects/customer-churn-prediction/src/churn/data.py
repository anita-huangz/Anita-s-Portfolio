"""Load and clean the Telco churn data.

Two things this fixes, both of which change results rather than tidiness.

**`TotalCharges` is not numeric.** Eleven rows hold a blank string. The
notebook coerced them to NaN and filled with the column mean, 2283.30 — which
tells the model that eleven brand-new customers have already paid two thousand
dollars. All eleven have `tenure == 0`: they signed up and have not been billed
yet, so the correct value is exactly 0, and it is derivable rather than
guessable.

**The dataset is right-censored survival data, not a labelled binary
problem.** `tenure` is how long a customer has been observed and `Churn` is
whether the observation ended in them leaving. 73.5% are censored — still
subscribed on the day the data was cut, so their eventual lifetime is unknown
and merely *at least* their current tenure. A classifier sees a one-month
customer who has not left and a six-year customer who has not left as the same
row. They are not remotely the same evidence.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

DATA = Path(__file__).resolve().parents[2] / "data" / "telco-customer-churn.csv"

#: Columns with no order to them. Encoding these as 0/1/2 invents one.
NOMINAL = [
    "gender", "Partner", "Dependents", "PhoneService", "MultipleLines",
    "InternetService", "OnlineSecurity", "OnlineBackup", "DeviceProtection",
    "TechSupport", "StreamingTV", "StreamingMovies", "PaperlessBilling",
    "PaymentMethod",
]

#: Contract genuinely is ordered: longer commitment, harder to leave.
ORDINAL = {"Contract": ["Month-to-month", "One year", "Two year"]}

NUMERIC = ["tenure", "MonthlyCharges", "TotalCharges", "SeniorCitizen"]

REQUIRED = {*NOMINAL, *ORDINAL, *NUMERIC, "customerID", "Churn"}


class SchemaError(ValueError):
    """The file is not the Telco churn dataset this package expects."""


@dataclass(frozen=True)
class Dataset:
    """Features, the binary label, and the survival pair.

    Carrying all three together is deliberate: the whole argument of this
    project is that the same rows support two different questions, and keeping
    the survival pair beside the label makes it hard to forget the second one.
    """

    frame: pd.DataFrame
    #: 1 if the customer left, 0 if they were still subscribed at the cutoff.
    event: np.ndarray
    #: Months observed. For a censored row this is a lower bound on lifetime.
    duration: np.ndarray

    def __len__(self) -> int:
        return len(self.frame)

    @property
    def churn_rate(self) -> float:
        return float(self.event.mean())

    @property
    def censoring_rate(self) -> float:
        """Share of customers whose eventual lifetime is unknown."""
        return float(1.0 - self.event.mean())

    @property
    def features(self) -> pd.DataFrame:
        return self.frame.drop(columns=["customerID", "Churn"])


def repair_total_charges(frame: pd.DataFrame) -> pd.Series:
    """`TotalCharges` as a number, with the blanks resolved rather than guessed.

    Returns the repaired column. Raises if a blank appears on a row with
    non-zero tenure, because then it is genuinely missing and filling it with
    zero would be the same class of mistake as filling it with the mean.
    """
    charges = pd.to_numeric(frame["TotalCharges"], errors="coerce")
    blank = charges.isna()
    if not blank.any():
        return charges

    unbilled = blank & (frame["tenure"] == 0)
    unexplained = blank & ~unbilled
    if unexplained.any():
        raise SchemaError(
            f"{int(unexplained.sum())} row(s) have no TotalCharges but non-zero "
            "tenure; that is missing data, not an unbilled new customer"
        )
    return charges.mask(unbilled, 0.0)


#: Levels that restate a column that is already in the table.
#:
#: Every add-on service has a "No internet service" level, and all six of them
#: are *identical* to `InternetService == "No"` -- the same 1,526 customers.
#: `MultipleLines == "No phone service"` likewise repeats `PhoneService ==
#: "No"`. Encoded as they stand, that is six perfectly collinear dummy columns:
#: the design matrix drops from rank 27 to 21 and the Cox Hessian is singular.
#:
#: Collapsing them to plain "No" loses nothing. A customer with no internet
#: does not have online security, and the table still says so twice over.
REDUNDANT_LEVELS = {
    "No internet service": "No",
    "No phone service": "No",
}


def collapse_redundant_levels(frame: pd.DataFrame) -> pd.DataFrame:
    """Replace levels that duplicate another column with plain "No"."""
    frame = frame.copy()
    for column in NOMINAL:
        # Not `dtype == object`: pandas 3.0 gives text columns a `str` dtype,
        # so that check silently matches nothing and the collapse never runs.
        if column in frame and not pd.api.types.is_numeric_dtype(frame[column]):
            frame[column] = frame[column].replace(REDUNDANT_LEVELS)
    return frame


def load(path: Path | str = DATA) -> Dataset:
    """Read the CSV and return a validated dataset."""
    frame = pd.read_csv(path)
    missing = REQUIRED - set(frame.columns)
    if missing:
        raise SchemaError(f"missing column(s): {sorted(missing)}")

    frame = frame.copy()
    frame["TotalCharges"] = repair_total_charges(frame)
    frame = collapse_redundant_levels(frame)

    labels = frame["Churn"].astype(str).str.strip().str.lower()
    unknown = set(labels.unique()) - {"yes", "no"}
    if unknown:
        raise SchemaError(f"Churn holds unexpected value(s): {sorted(unknown)}")

    event = (labels == "yes").to_numpy().astype(np.int8)
    duration = frame["tenure"].to_numpy().astype(float)

    if (duration < 0).any():
        raise SchemaError("negative tenure")
    # A customer who left at tenure 0 would be an event at time zero, which no
    # survival estimator can place. The dataset has none; assert it rather
    # than discovering it as a silent NaN much later.
    if ((duration == 0) & (event == 1)).any():
        raise SchemaError("a churn event at tenure 0 has no observable duration")

    return Dataset(frame=frame, event=event, duration=duration)


#: Excluded from the Cox design matrix, and not for tidiness.
#:
#: `tenure` is the time axis. Putting the duration on both sides of a
#: proportional-hazards model asks "given you have survived t months, how does
#: t affect your hazard" -- the answer is baked into the baseline, and the
#: coefficient it produces is an artefact.
#:
#: `TotalCharges` is worse, because the circularity is hidden: it is very
#: nearly `tenure x MonthlyCharges` (the two agree to within a dollar at the
#: median), so it smuggles the survival time back in wearing a different name.
SURVIVAL_EXCLUDED = ["tenure", "TotalCharges"]


def cox_design_matrix(data: Dataset, exclude: list[str] | None = None) -> pd.DataFrame:
    """Numeric design matrix for Cox regression.

    One-hot with the first level dropped, because a Cox model has no intercept
    -- the baseline hazard plays that role -- so keeping every level would make
    the matrix singular.
    """
    exclude = SURVIVAL_EXCLUDED if exclude is None else exclude
    features = data.features.drop(columns=[c for c in exclude if c in data.features])

    nominal = [c for c in NOMINAL if c in features]
    design = pd.get_dummies(features, columns=nominal, drop_first=True, dtype=float)
    if "Contract" in design:
        design["Contract"] = design["Contract"].map(
            {level: i for i, level in enumerate(ORDINAL["Contract"])}
        ).astype(float)
    return design.astype(float)


def collinearity_with_duration(data: Dataset) -> pd.Series:
    """How closely each numeric column tracks the survival time.

    Run before trusting a design matrix: anything near 1 is the duration in
    disguise and will produce a confident, meaningless coefficient.
    """
    numeric = data.features.select_dtypes("number")
    return (
        numeric.apply(lambda col: np.corrcoef(col, data.duration)[0, 1])
        .abs()
        .sort_values(ascending=False)
    )
