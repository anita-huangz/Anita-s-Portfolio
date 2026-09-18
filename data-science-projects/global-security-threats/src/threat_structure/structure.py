"""Does this dataset have any structure to find?

The original notebook ran six unsupervised methods -- PCA, t-SNE, K-Means,
DBSCAN, Isolation Forest, Local Outlier Factor -- and every one produced a
picture. That is what they do. None of them can tell you whether the picture
means anything, because unsupervised methods have no ground truth to be wrong
against: K-Means returns k clusters whatever you give it, and a projection of
independent noise still looks like a cloud with edges.

So this module asks the question that has to come first. Three tests, each on
a different kind of structure:

**Are the marginals anything but uniform?** Kolmogorov-Smirnov against a
uniform on the observed range.

**Are the categories anything but equally likely?** Chi-square against equal
proportions, with the multiplicity of testing seven columns stated.

**Is there any relationship between columns?** Cramer's V for category pairs,
Pearson for the numerics. A dataset of independent draws has neither.
"""

from __future__ import annotations

import itertools
from dataclasses import dataclass, field

import numpy as np
import pandas as pd
from scipy import stats

from .data import CATEGORICAL, NUMERIC, Incidents


@dataclass(frozen=True)
class UniformityTest:
    """Per-column Kolmogorov-Smirnov against a uniform on its own range."""

    frame: pd.DataFrame = field(default_factory=pd.DataFrame)

    @property
    def all_uniform(self) -> bool:
        return bool((self.frame["p"] > 0.05).all())

    @property
    def indistinguishable(self) -> list[str]:
        return sorted(self.frame.index[self.frame["p"] > 0.05])


def uniformity(data: Incidents) -> UniformityTest:
    """Test each numeric column against a uniform distribution.

    The range is taken from the data, so this is not testing "is it uniform on
    [0, 1]" but the weaker and more relevant "is it flat across whatever range
    it occupies". Real loss figures are heavy-tailed; flat ones were generated.
    """
    rows = {}
    for column in NUMERIC:
        values = data.frame[column].to_numpy(dtype=float)
        values = values[np.isfinite(values)]
        # `np.ptp(x)` rather than `x.ptp()`: the ndarray method was removed
        # in NumPy 2.
        reference = stats.uniform(loc=values.min(), scale=np.ptp(values))
        result = stats.kstest(values, reference.cdf)
        rows[column] = {"D": float(result.statistic), "p": float(result.pvalue)}
    return UniformityTest(frame=pd.DataFrame(rows).T.sort_values("p"))


@dataclass(frozen=True)
class BalanceTest:
    """Per-column chi-square against equal proportions."""

    frame: pd.DataFrame = field(default_factory=pd.DataFrame)

    @property
    def tests(self) -> int:
        return len(self.frame)

    @property
    def expected_false_positives(self) -> float:
        return 0.05 * self.tests

    @property
    def unbalanced(self) -> list[str]:
        return sorted(self.frame.index[self.frame["p"] <= 0.05])

    @property
    def consistent_with_chance(self) -> bool:
        """Are the rejections no more numerous than chance would give?

        With seven columns tested at p < 0.05, about 0.35 rejections are
        expected even if every column is perfectly balanced. Finding one is
        not evidence of imbalance, and reporting it as such is the mistake
        this property exists to prevent.
        """
        return len(self.unbalanced) <= max(1, round(self.expected_false_positives))


def balance(data: Incidents, extra: tuple[str, ...] = ("Year",)) -> BalanceTest:
    """Test each categorical column for equal category frequencies."""
    rows = {}
    for column in (*CATEGORICAL, *extra):
        if column not in data.frame:
            continue
        counts = data.frame[column].value_counts().to_numpy()
        result = stats.chisquare(counts)
        rows[column] = {
            "categories": len(counts),
            "chi2": float(result.statistic),
            "p": float(result.pvalue),
        }
    return BalanceTest(frame=pd.DataFrame(rows).T.sort_values("p"))


def cramers_v(a: pd.Series, b: pd.Series) -> float:
    """Association between two categorical columns, 0 to 1.

    Chi-square scaled by the table size, so it can be compared across pairs
    with different numbers of categories -- which raw chi-square cannot.
    """
    table = pd.crosstab(a, b).to_numpy()
    if min(table.shape) < 2:
        return 0.0
    chi2 = float(stats.chi2_contingency(table).statistic)
    n = table.sum()
    return float(np.sqrt(chi2 / (n * (min(table.shape) - 1))))


@dataclass(frozen=True)
class AssociationTest:
    """Every pairwise association, categorical and numeric."""

    categorical_pairs: pd.DataFrame = field(default_factory=pd.DataFrame)
    numeric_correlations: pd.DataFrame = field(default_factory=pd.DataFrame)

    @property
    def strongest_categorical(self) -> tuple[str, float]:
        top = self.categorical_pairs.iloc[0]
        return f"{top['a']} x {top['b']}", float(top["v"])

    @property
    def strongest_numeric(self) -> float:
        values = self.numeric_correlations.to_numpy(dtype=float).copy()
        np.fill_diagonal(values, 0.0)
        return float(np.abs(values).max())

    @property
    def independent(self) -> bool:
        """No pair of columns carries a usable relationship.

        The 0.1 cut-off is a judgement, and a generous one: a Cramer's V of
        0.1 is already a negligible association by any conventional reading.
        """
        return self.strongest_categorical[1] < 0.1 and self.strongest_numeric < 0.1


def associations(data: Incidents) -> AssociationTest:
    """Pairwise association across every column pair."""
    rows = []
    for a, b in itertools.combinations(CATEGORICAL, 2):
        rows.append({"a": a, "b": b, "v": cramers_v(data.frame[a], data.frame[b])})
    pairs = pd.DataFrame(rows).sort_values("v", ascending=False).reset_index(drop=True)
    return AssociationTest(
        categorical_pairs=pairs,
        numeric_correlations=data.numeric.corr(),
    )
