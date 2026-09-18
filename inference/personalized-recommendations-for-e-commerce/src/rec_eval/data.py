"""Load the two tables, and be clear about what they do and do not contain.

**There is no user-item interaction matrix.** Customers carry a
`Purchase_History` of subcategory *names* -- `['Biography', 'Jeans']` -- and
products carry IDs that appear nowhere in the customer table. So collaborative
filtering is not merely difficult here, it is undefined: there is no "users who
bought this also bought" to compute, because no purchase is attached to a
product.

What the data does support is content-based recommendation over the 24
subcategories the two tables share, and that can be evaluated properly. The
original notebook instead trained classifiers on product attributes to predict
`Probability_of_Recommendation`, which is a regression on a column of uniform
noise and is not recommendation at all.

One more thing to know before trusting any result: **purchase history is
generated from browsing history.** Every customer's browsing categories
contain at least one category they purchased from -- all 10,000 of them. A
model given browsing history to predict purchases is reading the answer.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

DATA = Path(__file__).resolve().parents[2] / "data"
CUSTOMERS = DATA / "customer_data_collection.csv"
PRODUCTS = DATA / "product_recommendation_data.csv"


class SchemaError(ValueError):
    """The files are not the dataset this package expects."""


def _parse_list(value) -> list[str]:
    """Read a Python-literal list out of a CSV cell.

    `ast.literal_eval` rather than `eval`: the cells come from a file and
    nothing here should be able to execute what it reads.
    """
    if isinstance(value, list):
        return value
    if not isinstance(value, str) or not value.strip():
        return []
    try:
        parsed = ast.literal_eval(value)
    except (ValueError, SyntaxError):
        return []
    return [str(item) for item in parsed] if isinstance(parsed, list) else []


@dataclass(frozen=True)
class Catalogue:
    """Products, and the subcategory taxonomy they define."""

    frame: pd.DataFrame

    def __len__(self) -> int:
        return len(self.frame)

    @property
    def subcategories(self) -> list[str]:
        return sorted(self.frame["Subcategory"].unique())

    @property
    def category_of(self) -> dict[str, str]:
        """Subcategory -> its category. Each subcategory has exactly one."""
        return (
            self.frame.groupby("Subcategory")["Category"]
            .agg(lambda s: s.mode().iloc[0])
            .to_dict()
        )

    def popularity(self) -> pd.Series:
        """How often each subcategory appears in the catalogue.

        The baseline any recommender has to beat, and frequently does not.
        """
        return self.frame["Subcategory"].value_counts()


@dataclass(frozen=True)
class Customers:
    """Customers, with their history parsed out of the CSV's string lists."""

    frame: pd.DataFrame
    purchases: list[list[str]]
    browsing: list[list[str]]

    def __len__(self) -> int:
        return len(self.frame)

    @property
    def with_enough_history(self) -> list[int]:
        """Rows with at least two purchases.

        Leave-one-out needs something left over after holding one out, so a
        customer with a single purchase cannot be evaluated -- and a third of
        them have exactly one. Dropping them silently would overstate the
        sample; this makes the count visible.
        """
        return [i for i, items in enumerate(self.purchases) if len(set(items)) >= 2]


def load_catalogue(path: Path | str = PRODUCTS) -> Catalogue:
    frame = pd.read_csv(path)
    missing = {"Product_ID", "Category", "Subcategory"} - set(frame.columns)
    if missing:
        raise SchemaError(f"products missing column(s): {sorted(missing)}")
    frame = frame.copy()
    frame["similar"] = frame.get(
        "Similar_Product_List", pd.Series([[]] * len(frame))
    ).map(_parse_list)
    return Catalogue(frame=frame)


def load_customers(path: Path | str = CUSTOMERS) -> Customers:
    frame = pd.read_csv(path)
    missing = {"Customer_ID", "Purchase_History", "Browsing_History"} - set(frame.columns)
    if missing:
        raise SchemaError(f"customers missing column(s): {sorted(missing)}")
    return Customers(
        frame=frame,
        purchases=[_parse_list(v) for v in frame["Purchase_History"]],
        browsing=[_parse_list(v) for v in frame["Browsing_History"]],
    )


@dataclass(frozen=True)
class BrowsingLeak:
    """Does browsing history already contain the purchase answer?"""

    customers: int
    matching: int

    @property
    def rate(self) -> float:
        return self.matching / self.customers if self.customers else float("nan")

    @property
    def is_deterministic(self) -> bool:
        """Near 1.0 means purchases were generated from browsing.

        Which makes "predict purchases from browsing" a lookup rather than a
        prediction, and any accuracy from it meaningless.
        """
        return self.rate > 0.99


def browsing_leak(customers: Customers, catalogue: Catalogue) -> BrowsingLeak:
    """How often a customer's browsing categories cover a purchase."""
    category_of = catalogue.category_of
    matching = 0
    for browsed, bought in zip(customers.browsing, customers.purchases, strict=True):
        purchased_categories = {category_of.get(item) for item in bought}
        if set(browsed) & purchased_categories:
            matching += 1
    return BrowsingLeak(customers=len(customers), matching=matching)
