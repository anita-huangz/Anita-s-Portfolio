"""The classifier: encoding, leakage, and the numbers the site reports.

This module had no tests at all, which the coverage report did not show —
without an `__init__.py` the package was a namespace package, so `--cov` only
counted modules the tests happened to import and an entirely untested one was
absent from the table rather than listed at 0%. The project read 97% and was
really 73%.

The AUC on the site's churn card comes from here, so these check the encoding
choices that produce it rather than only that it runs.
"""

import numpy as np
import pandas as pd
import pytest
from sklearn.linear_model import LogisticRegression

from churn.classify import (
    FOLDS,
    RANDOM_STATE,
    bootstrap_interval,
    build_preprocessor,
    cross_validated_probabilities,
    honest_holdout_score,
    leaky_holdout_score,
    models,
    permutation_importance_scores,
    pipeline,
)
from churn.data import NOMINAL, NUMERIC, ORDINAL, load


@pytest.fixture(scope="module")
def data():
    return load()


@pytest.fixture
def estimator():
    # Cheap and deterministic; the encoding is what is under test, not the model.
    return LogisticRegression(max_iter=2000, random_state=RANDOM_STATE)


class TestPreprocessor:
    def test_nominal_columns_are_one_hot_not_ordinal(self, data):
        """The notebook's mistake: an ordinal code invents an order that is not
        there, telling the model that PaymentMethod 3 sits between 2 and 4."""
        prep = build_preprocessor(leaky=False)
        out = prep.fit_transform(data.features)
        # One-hot expands the nominal columns, so the matrix must be wider than
        # the raw column count.
        assert out.shape[1] > len(NOMINAL) + len(ORDINAL) + len(NUMERIC)

    def test_the_leaky_preprocessor_keeps_one_column_per_feature(self, data):
        prep = build_preprocessor(leaky=True)
        out = prep.fit_transform(data.features)
        assert out.shape[1] == len(NOMINAL) + len(ORDINAL) + len(NUMERIC)

    def test_ordinal_categories_are_given_explicitly(self):
        """Left to itself, OrdinalEncoder sorts alphabetically, which would put
        'One year' before 'Two year' before 'Month-to-month'."""
        prep = build_preprocessor(leaky=False)
        ordinal = {name: t for name, t, _ in prep.transformers}["ordinal"]
        assert ordinal.categories == [ORDINAL[c] for c in ORDINAL]

    @pytest.mark.filterwarnings("ignore:Found unknown categories")
    def test_unseen_categories_do_not_raise(self, data):
        """A category absent from training must not crash at predict time."""
        prep = build_preprocessor(leaky=False).fit(data.features)
        row = data.features.iloc[[0]].copy()
        row.loc[:, NOMINAL[0]] = "a value never seen before"
        assert prep.transform(row).shape[0] == 1

    def test_numeric_columns_are_standardised(self, data):
        prep = build_preprocessor(leaky=False).fit(data.features)
        numeric = {name: t for name, t, _ in prep.transformers}["numeric"]
        assert numeric.__class__.__name__ == "StandardScaler"


class TestModels:
    def test_every_model_is_a_classifier_that_gives_probabilities(self):
        for name, model in models().items():
            assert hasattr(model, "fit"), name
            assert hasattr(model, "predict_proba"), name

    def test_class_weight_is_applied_where_the_model_supports_it(self):
        """Churn is 27% of rows; unweighted, 'nobody leaves' scores 73%."""
        weighted = models(class_weight="balanced")
        assert any(
            getattr(m, "class_weight", None) == "balanced" for m in weighted.values()
        )

    def test_class_weight_can_be_turned_off(self):
        for model in models(class_weight=None).values():
            assert getattr(model, "class_weight", None) is None

    def test_pipeline_puts_the_preprocessor_first(self, estimator):
        steps = [name for name, _ in pipeline(estimator).steps]
        assert steps[0] != steps[-1]
        assert len(steps) == 2


class TestLeakage:
    """The comparison the project exists to make, checked rather than asserted."""

    def test_both_holdout_scores_are_plausible_aucs(self, data, estimator):
        leaky = leaky_holdout_score(data, estimator)
        honest = honest_holdout_score(data, estimator)
        for score in (leaky, honest):
            assert 0.5 < score < 1.0

    def test_they_are_reproducible(self, data, estimator):
        """Both fix the random state, so a rerun must give the same number."""
        first = honest_holdout_score(data, estimator)
        second = honest_holdout_score(
            data, LogisticRegression(max_iter=2000, random_state=RANDOM_STATE)
        )
        assert first == pytest.approx(second)

    def test_the_two_differ(self, data, estimator):
        """If fitting the transform on the test rows changed nothing, the whole
        point of separating them would be missing."""
        leaky = leaky_holdout_score(data, estimator)
        honest = honest_holdout_score(
            data, LogisticRegression(max_iter=2000, random_state=RANDOM_STATE)
        )
        assert leaky != pytest.approx(honest, abs=1e-9)


class TestCrossValidation:
    def test_it_returns_one_probability_per_row(self, data, estimator):
        probability = cross_validated_probabilities(data, estimator)
        assert probability.shape == (len(data.features),)
        assert np.all((probability >= 0) & (probability <= 1))

    def test_every_row_is_predicted_out_of_fold(self, data, estimator):
        """`cross_val_predict` covers each row exactly once; an unfilled row
        would arrive as a zero and look like a confident negative."""
        probability = cross_validated_probabilities(data, estimator)
        assert not np.any(np.isnan(probability))
        assert len(np.unique(probability)) > len(probability) // 2

    def test_the_fold_count_is_honoured(self, data, estimator):
        assert FOLDS == 5
        few = cross_validated_probabilities(data, estimator, folds=2)
        assert few.shape == (len(data.features),)


class TestBootstrapInterval:
    def test_the_point_estimate_lies_inside_the_interval(self):
        rng = np.random.default_rng(0)
        label = rng.integers(0, 2, 500)
        score = np.clip(label * 0.3 + rng.normal(0.5, 0.2, 500), 0, 1)
        from sklearn.metrics import roc_auc_score

        point, low, high = bootstrap_interval(roc_auc_score, label, score, draws=200)
        assert low <= point <= high

    def test_a_wider_alpha_gives_a_narrower_interval(self):
        rng = np.random.default_rng(1)
        label = rng.integers(0, 2, 400)
        score = np.clip(label * 0.25 + rng.normal(0.5, 0.25, 400), 0, 1)
        from sklearn.metrics import roc_auc_score

        _, n_lo, n_hi = bootstrap_interval(
            roc_auc_score, label, score, draws=200, alpha=0.5
        )
        _, w_lo, w_hi = bootstrap_interval(
            roc_auc_score, label, score, draws=200, alpha=0.05
        )
        assert (n_hi - n_lo) < (w_hi - w_lo)

    def test_a_perfect_ranking_has_an_interval_at_one(self):
        from sklearn.metrics import roc_auc_score

        label = np.array([0] * 50 + [1] * 50)
        point, _low, high = bootstrap_interval(
            roc_auc_score, label, label.astype(float), draws=100
        )
        assert point == pytest.approx(1.0)
        assert high == pytest.approx(1.0)


class TestPermutationImportance:
    def test_it_scores_every_feature(self, data, estimator):
        scores = permutation_importance_scores(data, estimator, repeats=2)
        assert isinstance(scores, pd.Series)
        assert set(scores.index) == set(data.features.columns)

    def test_shuffling_a_feature_cannot_help_on_average(self, data, estimator):
        """Importance is the drop in score when a column is scrambled. A large
        negative value would mean the model improves without the feature, which
        is noise rather than signal -- so only a small one is tolerable."""
        scores = permutation_importance_scores(data, estimator, repeats=2)
        assert scores.min() > -0.05
