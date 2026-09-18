"""Structure tests, clustering against a null, and detector agreement.

Each test that reports "no structure" on this dataset is paired with one on
synthetic data built to contain structure, so the method is shown to work
rather than merely to return the convenient answer.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from threat_structure.anomalies import (
    Agreement,
    detector_agreement,
    isolation_forest_flags,
    local_outlier_flags,
    tail_checks,
)
from threat_structure.clustering import (
    compare_with_null,
    fit_kmeans,
    gap_statistic,
    stability,
)
from threat_structure.data import (
    CATEGORICAL,
    NUMERIC,
    Incidents,
    SchemaError,
    load,
    shuffle_within_columns,
)
from threat_structure.structure import (
    associations,
    balance,
    cramers_v,
    uniformity,
)


@pytest.fixture(scope="module")
def data():
    return load()


def clustered(n=900, spread=0.25, seed=0) -> Incidents:
    """Synthetic incidents with three genuine, well-separated groups."""
    rng = np.random.default_rng(seed)
    centres = np.array([[10.0, 100_000.0, 5.0], [50.0, 500_000.0, 35.0],
                        [90.0, 900_000.0, 65.0]])
    which = rng.integers(0, 3, n)
    numeric = centres[which] * (1 + rng.normal(0, spread, (n, 3)))
    frame = pd.DataFrame(numeric, columns=NUMERIC)
    # Categories that also track the group, so the structure is not numeric-only.
    for i, column in enumerate(CATEGORICAL):
        frame[column] = [f"{column[:3]}{(w + i) % 3}" for w in which]
    return Incidents(frame=frame)


# --------------------------------------------------------------------------- #
# Structure
# --------------------------------------------------------------------------- #


def test_the_dataset_loads(data):
    assert len(data) == 3000
    assert data.encoded().shape == (3000, 39)


def test_a_missing_column_is_caught(tmp_path):
    path = tmp_path / "bad.csv"
    pd.DataFrame({"Country": ["UK"]}).to_csv(path, index=False)
    with pytest.raises(SchemaError, match="missing column"):
        load(path)


def test_every_numeric_column_is_indistinguishable_from_uniform(data):
    """Real loss figures are heavy-tailed. Flat ones were generated."""
    result = uniformity(data)
    assert result.all_uniform
    assert len(result.indistinguishable) == 3
    assert (result.frame["p"] > 0.3).all()


def test_the_uniformity_test_rejects_a_skewed_column():
    rng = np.random.default_rng(1)
    frame = pd.DataFrame(
        {c: rng.lognormal(0, 1, 2000) for c in NUMERIC}
        | {c: "x" for c in CATEGORICAL}
    )
    assert not uniformity(Incidents(frame=frame)).all_uniform


def test_the_categories_are_consistent_with_being_equally_likely(data):
    """One column clears p < 0.05, which is what seven tests give by chance."""
    result = balance(data)
    assert result.consistent_with_chance
    assert len(result.unbalanced) <= 1
    assert result.expected_false_positives == pytest.approx(0.35)


def test_the_balance_test_detects_a_genuinely_skewed_column():
    frame = pd.DataFrame(
        {c: 1.0 for c in NUMERIC}
        | {c: ["a"] * 1900 + ["b"] * 100 for c in CATEGORICAL},
        index=range(2000),
    )
    result = balance(Incidents(frame=frame), extra=())
    assert not result.consistent_with_chance


def test_no_pair_of_columns_carries_a_relationship(data):
    result = associations(data)
    assert result.independent
    _, strength = result.strongest_categorical
    assert strength < 0.1
    assert result.strongest_numeric < 0.05


def test_the_association_measure_finds_a_real_dependency():
    values = ["a", "b", "c"] * 300
    assert cramers_v(pd.Series(values), pd.Series(values)) > 0.9
    rng = np.random.default_rng(2)
    assert cramers_v(pd.Series(values), pd.Series(rng.permutation(values))) < 0.15


def test_shuffling_preserves_the_marginals_and_destroys_the_joint(data):
    """Which is what makes it the right null."""
    shuffled = shuffle_within_columns(data.frame, seed=0)
    for column in CATEGORICAL:
        assert (
            data.frame[column].value_counts().sort_index()
            == shuffled[column].value_counts().sort_index()
        ).all()
    for column in NUMERIC:
        assert data.frame[column].sum() == pytest.approx(shuffled[column].sum())


# --------------------------------------------------------------------------- #
# Clustering
# --------------------------------------------------------------------------- #


def test_kmeans_returns_k_clusters_whatever_it_is_given(data):
    """The reason a silhouette score is not evidence.

    3,000 points of independent noise still come back as four tidy groups.
    """
    labels = fit_kmeans(data.encoded(), 4)
    assert len(np.unique(labels)) == 4


def test_the_clusters_are_no_better_than_shuffled_columns(data):
    """The finding: the silhouette is geometry, not structure.

    Shuffling every column independently keeps each marginal exactly and
    destroys every relationship between them. The score does not move.
    """
    result = compare_with_null(data, k=4, draws=20)
    assert not result.better_than_noise
    assert result.p_value > 0.05
    assert abs(result.observed - result.null_mean) < 0.01


def test_real_clusters_beat_the_null_comfortably():
    result = compare_with_null(clustered(), k=3, draws=25)
    assert result.better_than_noise
    assert result.observed > result.null_mean + 0.2


def test_the_clustering_is_not_stable_under_resampling(data):
    """Real clusters survive a bootstrap. An arbitrary partition is redrawn."""
    result = stability(data, k=4, draws=12)
    assert not result.stable
    assert result.mean_ari < 0.75


def test_real_clusters_are_stable(data):
    result = stability(clustered(), k=3, draws=12)
    assert result.stable
    assert result.mean_ari > 0.75


def test_the_gap_statistic_says_there_are_no_clusters(data):
    """The only criterion here that *can* say that.

    Silhouette and elbow plots are undefined at k = 1, so they are
    structurally incapable of reporting "no clusters" however hard you squint
    at them.
    """
    result = gap_statistic(data, max_k=5, references=5)
    assert result.says_no_clusters
    assert result.best_k == 1


def test_the_gap_statistic_finds_the_right_k_when_there_is_one():
    result = gap_statistic(clustered(), max_k=5, references=5)
    assert result.best_k > 1


def test_the_gap_falls_with_k_on_uniform_data(data):
    """The signature of noise: adding clusters never helps."""
    frame = gap_statistic(data, max_k=4, references=5).frame
    gaps = frame["gap"].to_numpy()
    assert (np.diff(gaps) < 0).all()


# --------------------------------------------------------------------------- #
# Anomalies
# --------------------------------------------------------------------------- #


def test_both_detectors_flag_the_requested_share(data):
    matrix = data.encoded()
    assert isolation_forest_flags(matrix, contamination=0.05).sum() == 150
    assert local_outlier_flags(matrix, contamination=0.05).sum() == 150


def test_chance_overlap_is_computed_not_assumed():
    """Two detectors flagging 150 of 3,000 overlap on 7.5 rows by coincidence."""
    agreement = Agreement(n=3000, flagged_a=150, flagged_b=150, overlap=30)
    assert agreement.expected_overlap == pytest.approx(7.5)
    assert agreement.excess == pytest.approx(4.0)


def test_the_detectors_agree_but_that_is_not_validation(data):
    """Agreement rules out one being broken. It says nothing about the rows.

    Both rank distance from the centre of the same cloud, so they agree on
    uniform noise too -- which is exactly the situation here.
    """
    agreement = detector_agreement(data)
    assert agreement.agree
    assert agreement.excess > 2


def test_the_flagged_rows_are_not_a_single_columns_tail(data):
    """So the multivariate machinery is doing something a `sort` would not.

    What it is doing is finding rare *combinations* of categories -- which on
    independent uniform columns occur at random.
    """
    checks = tail_checks(data)
    assert not any(check.is_just_a_tail for check in checks)
    assert all(0.25 < check.flagged_mean_percentile < 0.75 for check in checks)


def test_a_planted_outlier_column_is_recognised_as_a_tail():
    rng = np.random.default_rng(3)
    n = 1000
    values = rng.uniform(0, 100, n)
    values[:50] = rng.uniform(5_000, 10_000, 50)  # a clear tail
    frame = pd.DataFrame({NUMERIC[0]: values})
    frame[NUMERIC[1]] = rng.uniform(0, 100, n)
    frame[NUMERIC[2]] = rng.uniform(0, 100, n)
    for column in CATEGORICAL:
        frame[column] = "x"
    checks = tail_checks(Incidents(frame=frame))
    assert checks[0].is_just_a_tail


def test_the_dataset_is_a_real_file_not_an_lfs_pointer():
    from threat_structure.data import DATA

    assert not DATA.read_text().splitlines()[0].startswith("version https://git-lfs")
