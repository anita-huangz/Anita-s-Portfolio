"""Load the dataset, and find out what is actually in it.

The original notebook ran TF-IDF over the article text, added sentiment and
metadata features, compared several classifiers under cross-validation, and
reported accuracy. Every one of those steps works on this file. None of them
should have been run, because the file does not contain articles.

Every title is `Breaking News {i}` and every body is `This is the content of
article {i}. It contains detailed analysis and reports.` -- the row index in
prose. Strip the digits and 4,000 distinct titles collapse to one. So a TF-IDF
model over this "text" is a model of the row number.

The labels are then assigned at random, which is harder to see and is what the
rest of this package is for: showing absence of signal is a different and more
demanding job than failing to find any.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

DATA = Path(__file__).resolve().parents[2] / "data" / "fake_news_dataset.csv"

TEXT_COLUMNS = ["title", "text", "author", "source", "category", "state"]
NUMERIC_FEATURES = [
    "sentiment_score", "word_count", "char_count", "has_images", "has_videos",
    "readability_score", "num_shares", "num_comments", "is_satirical",
    "trust_score", "source_reputation", "clickbait_score", "plagiarism_score",
]
CATEGORICAL_FEATURES = ["political_bias", "fact_check_rating", "category", "source", "state"]

_DIGITS = re.compile(r"\d+")


class SchemaError(ValueError):
    """The file is not the dataset this package expects."""


@dataclass(frozen=True)
class Dataset:
    frame: pd.DataFrame
    label: np.ndarray

    def __len__(self) -> int:
        return len(self.frame)

    @property
    def fake_rate(self) -> float:
        return float(self.label.mean())

    @property
    def features(self) -> pd.DataFrame:
        keep = [c for c in (*NUMERIC_FEATURES, *CATEGORICAL_FEATURES) if c in self.frame]
        return self.frame[keep]


def load(path: Path | str = DATA) -> Dataset:
    frame = pd.read_csv(path)
    if "label" not in frame:
        raise SchemaError("no 'label' column")
    labels = frame["label"].astype(str).str.strip().str.lower()
    unknown = set(labels.unique()) - {"fake", "real"}
    if unknown:
        raise SchemaError(f"unexpected label(s): {sorted(unknown)}")
    return Dataset(frame=frame, label=(labels == "fake").to_numpy().astype(int))


@dataclass(frozen=True)
class TemplateReport:
    """How much of a text column is template and how much is content."""

    column: str
    rows: int
    distinct: int
    distinct_after_removing_digits: int
    example: str

    @property
    def is_templated(self) -> bool:
        """Many distinct strings that *collapse* once the digits are removed.

        The test is about collapse, not about the absolute count. An earlier
        version flagged anything with few skeletons, which called a column of
        five author names a template -- five names are not a template, they
        are five names. What makes `Breaking News 1..4000` a template is that
        4,000 distinct values become 1.
        """
        return self.distinct >= 20 and self.information_ratio < 0.05

    @property
    def information_ratio(self) -> float:
        """Distinct skeletons per distinct string.

        1.0 means every row says something different. Near zero means the only
        thing varying is the number.
        """
        return self.distinct_after_removing_digits / max(self.distinct, 1)


def template_report(frame: pd.DataFrame, column: str) -> TemplateReport:
    """Strip digits and count what is left.

    The cheapest possible test for "is this real text", and the one that would
    have stopped the original analysis before the first model was fitted.
    """
    if column not in frame:
        raise SchemaError(f"no column {column!r}")
    values = frame[column].astype(str)
    skeletons = values.map(lambda s: _DIGITS.sub("#", s))
    return TemplateReport(
        column=column,
        rows=len(values),
        distinct=int(values.nunique()),
        distinct_after_removing_digits=int(skeletons.nunique()),
        example=str(values.iloc[0]),
    )


def label_index_correlation(data: Dataset) -> float:
    """Does the label track the row order?

    Worth checking before trusting any text model on this file. The "text" is
    the row index spelled out, so if the labels were sorted or blocked, a
    TF-IDF model would score well by reading the number -- a real and very
    convincing-looking artefact. Here it is near zero, which means the file is
    shuffled, not that the trap does not exist.
    """
    position = np.arange(len(data), dtype=float)
    return float(np.corrcoef(position, data.label)[0, 1])
