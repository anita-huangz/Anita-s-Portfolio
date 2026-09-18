"""Extract chartable results by importing the data-science projects.

Each project is now an installed package with the analysis in it, so this
calls into them rather than re-deriving anything. That matters: a generator
that reimplements the modelling drifts from the package, and the chart then
keeps showing an answer the project no longer gives. An earlier version of
this file did exactly that.

Everything is seeded. A chart that changes between runs is not a result.

    python site/scripts/generate_notebook_results.py
"""

from __future__ import annotations

import json
import sys
import warnings
from pathlib import Path

import numpy as np

warnings.filterwarnings("ignore")

SEED = 42
ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data-science-projects"
OUT = ROOT / "site" / "src" / "data" / "demos"


def use(project: str) -> None:
    """Put a project's `src` on the import path.

    The projects are not installed into this environment -- CI checks out the
    repo and runs the generator, it does not pip-install seven packages -- so
    the path is extended explicitly.
    """
    path = str(DATA / project / "src")
    if path not in sys.path:
        sys.path.insert(0, path)


def write(name: str, payload: object) -> None:
    path = OUT / name
    path.write_text(json.dumps(payload, separators=(",", ":"), default=str) + "\n")
    print(f"  {name:<30} {path.stat().st_size / 1024:6.1f} KB")


def roc_points(y_true, scores, n: int = 60) -> list[dict]:
    """Downsampled ROC curve. A full curve is thousands of near-identical points."""
    from sklearn.metrics import roc_curve

    fpr, tpr, _ = roc_curve(y_true, scores)
    idx = np.unique(np.linspace(0, len(fpr) - 1, n).astype(int))
    return [{"x": round(float(fpr[i]), 4), "y": round(float(tpr[i]), 4)} for i in idx]


# --------------------------------------------------------------------------- #
# Customer churn
# --------------------------------------------------------------------------- #


def churn() -> None:
    """Import the project rather than re-deriving it.

    The previous version built its own model here, which meant the browser
    demo and the package could drift apart -- and it reproduced the bug the
    package fixes, dropping the eleven unbilled customers instead of setting
    their TotalCharges to zero.
    """
    use("customer-churn-prediction")

    from churn.calibration import (
        brier_skill_score,
        expected_calibration_error,
        reliability_curve,
    )
    from churn.classify import (
        cross_validated_probabilities,
        models,
        permutation_importance_scores,
    )
    from churn.data import cox_design_matrix, load
    from churn.economics import (
        Campaign,
        best_threshold,
        customer_value,
        expected_months_remaining,
        expected_value_curve,
        targeting_comparison,
    )
    from churn.survival import concordance_index, fit_cox, kaplan_meier, log_rank_test
    from sklearn.metrics import confusion_matrix, roc_auc_score

    data = load(DATA / "customer-churn-prediction" / "data" / "telco-customer-churn.csv")

    # Out-of-fold probabilities, so every score in the browser comes from a
    # fold the customer was not in.
    proba = cross_validated_probabilities(data, models(class_weight=None)["logistic"])
    balanced = cross_validated_probabilities(data, models()["logistic"])
    predicted = (proba >= 0.5).astype(int)
    tn, fp, fn, tp = confusion_matrix(data.event, predicted).ravel()

    # --- survival ---
    overall = kaplan_meier(data.duration, data.event)
    curves = []
    for contract in ["Month-to-month", "One year", "Two year"]:
        mask = (data.frame.Contract == contract).to_numpy()
        km = kaplan_meier(data.duration[mask], data.event[mask])
        grid = np.arange(0, 73, dtype=float)
        curves.append(
            {
                "label": contract,
                "count": int(mask.sum()),
                "survival": [round(float(v), 4) for v in km.predict(grid)],
            }
        )
    lower, upper = overall.confidence_interval()
    grid = np.arange(0, 73, dtype=float)
    band_lo = np.interp(grid, overall.times, lower, left=1.0)
    band_hi = np.interp(grid, overall.times, upper, left=1.0)
    logrank = log_rank_test(data.duration, data.event, data.frame.Contract.to_numpy())

    # --- Cox ---
    X = cox_design_matrix(data)
    cox = fit_cox(X, data.duration, data.event)
    summary = cox.summary().head(8)

    # --- economics, driven by each customer's own survival curve ---
    campaign = Campaign()
    months = expected_months_remaining(
        cox.predict_survival(X, grid[1:]), grid[1:], campaign.horizon_months
    )
    value = customer_value(data.frame.MonthlyCharges.to_numpy(float), months, campaign)
    ev = expected_value_curve(proba, data.event, value, campaign)
    best = best_threshold(ev)

    reliability = reliability_curve(balanced, data.event)
    honest_reliability = reliability_curve(proba, data.event)

    write(
        "nb-churn.json",
        {
            "rows": len(data),
            "churn_rate": round(float(data.churn_rate), 4),
            "censoring_rate": round(float(data.censoring_rate), 4),
            "auc": round(float(roc_auc_score(data.event, proba)), 4),
            "accuracy": round(float((predicted == data.event).mean()), 4),
            "precision": round(float(tp / (tp + fp)), 4),
            "recall": round(float(tp / (tp + fn)), 4),
            "confusion": {"tn": int(tn), "fp": int(fp), "fn": int(fn), "tp": int(tp)},
            "roc": roc_points(data.event, proba),
            "scores": [
                {"p": round(float(pr), 4), "y": int(t)}
                for pr, t in zip(proba, data.event, strict=True)
            ],
            # Permutation importance on held-out rows, not the tree's built-in
            # impurity importance -- that is computed on the training data and
            # inflates high-cardinality columns whether or not they generalise.
            "importances": [
                {"feature": f, "weight": round(float(w), 5)}
                for f, w in permutation_importance_scores(
                    data, models()["random_forest"]
                ).head(12).items()
            ],
            "by_contract": [
                {
                    "label": c["label"],
                    "rate": round(
                        float(
                            data.event[
                                (data.frame.Contract == c["label"]).to_numpy()
                            ].mean()
                        ),
                        4,
                    ),
                    "count": c["count"],
                }
                for c in curves
            ],
            "survival": {
                "months": [int(t) for t in grid],
                "overall": [round(float(v), 4) for v in overall.predict(grid)],
                "lower": [round(float(v), 4) for v in band_lo],
                "upper": [round(float(v), 4) for v in band_hi],
                "by_contract": curves,
                "median": None,  # never reached inside the window
                "restricted_mean_60": round(float(overall.restricted_mean(60)), 2),
                "logrank_chi2": round(float(logrank.statistic), 1),
                "concordance": round(
                    float(concordance_index(cox.risk_score(X), data.duration, data.event)),
                    4,
                ),
            },
            "hazard_ratios": [
                {
                    "name": name,
                    "hr": round(float(row.hazard_ratio), 3),
                    "lower": round(float(row.hr_lower), 3),
                    "upper": round(float(row.hr_upper), 3),
                }
                for name, row in summary.iterrows()
            ],
            "calibration": {
                "balanced": {
                    "auc": round(float(roc_auc_score(data.event, balanced)), 4),
                    "mean_predicted": round(float(balanced.mean()), 4),
                    "ece": round(float(expected_calibration_error(balanced, data.event)), 4),
                    "skill": round(float(brier_skill_score(balanced, data.event)), 4),
                    "bins": _bins(reliability),
                },
                "unweighted": {
                    "auc": round(float(roc_auc_score(data.event, proba)), 4),
                    "mean_predicted": round(float(proba.mean()), 4),
                    "ece": round(float(expected_calibration_error(proba, data.event)), 4),
                    "skill": round(float(brier_skill_score(proba, data.event)), 4),
                    "bins": _bins(honest_reliability),
                },
            },
            "economics": {
                "offer_cost": campaign.offer_cost,
                "acceptance": campaign.acceptance,
                "margin": campaign.margin,
                "horizon": campaign.horizon_months,
                "median_value": round(float(np.median(value)), 2),
                "best_threshold": round(float(best.threshold), 2),
                "curve": [
                    {
                        "t": round(float(r.threshold), 2),
                        "value": round(float(r.expected_value), 0),
                        "targeted": r.targeted,
                    }
                    for r in ev
                    if r.threshold <= 1.0
                ],
                "policies": {
                    k: round(float(v), 0)
                    for k, v in targeting_comparison(
                        proba, data.event, value, campaign, budget=1000
                    ).items()
                },
                # Per-customer value, so the browser can re-rank on any policy.
                "value": [round(float(v), 1) for v in value],
            },
        },
    )


def _bins(curve) -> list[dict]:
    return [
        {
            "predicted": round(float(p), 4),
            "observed": round(float(o), 4),
            "count": int(n),
        }
        for p, o, n in zip(curve.predicted, curve.observed, curve.count, strict=True)
        if n > 0
    ]


# --------------------------------------------------------------------------- #
# Fake news
# --------------------------------------------------------------------------- #


def fake_news() -> None:
    """The null result, as the package establishes it.

    The previous version trained a classifier and reported its AUC and feature
    importances -- the framing the project now rejects, because the text
    column is the row index and the labels are random.
    """
    use("fake-news-detection")

    from news_signal.data import TEXT_COLUMNS, load, template_report
    from news_signal.signal import (
        cross_validated_auc,
        feature_tests,
        gradient_boosting,
        learning_curve,
        minimum_detectable_auc,
        permutation_test,
    )

    data = load(DATA / "fake-news-detection" / "data" / "fake_news_dataset.csv")

    templates = []
    for column in TEXT_COLUMNS:
        if column not in data.frame:
            continue
        report = template_report(data.frame, column)
        templates.append(
            {
                "column": column,
                "distinct": report.distinct,
                "skeletons": report.distinct_after_removing_digits,
                "templated": bool(report.is_templated),
                "example": report.example[:90],
            }
        )

    permutation = permutation_test(data, permutations=200)
    effect = minimum_detectable_auc(len(data), int(data.label.sum()))
    curve = learning_curve(data)
    features = feature_tests(data)

    # Histogram of the null, so the browser can draw the distribution rather
    # than quote its mean.
    counts, edges = np.histogram(permutation.null_scores, bins=24)
    low, high = permutation.null_interval()

    write(
        "nb-fakenews.json",
        {
            "rows": len(data),
            "fake_rate": round(float(data.fake_rate), 4),
            "templates": templates,
            "observed_auc": round(float(permutation.observed), 4),
            "boosted_auc": round(
                float(cross_validated_auc(data, gradient_boosting())), 4
            ),
            "permutation": {
                "draws": permutation.permutations,
                "null_mean": round(float(permutation.null_mean), 4),
                "null_std": round(float(permutation.null_std), 4),
                "low": round(float(low), 4),
                "high": round(float(high), 4),
                "z": round(float(permutation.z_score), 3),
                "p": round(float(permutation.p_value), 4),
                "distinguishable": bool(permutation.distinguishable),
                "histogram": [
                    {
                        "x": round(float((edges[i] + edges[i + 1]) / 2), 4),
                        "n": int(counts[i]),
                    }
                    for i in range(len(counts))
                ],
            },
            "power": {
                "minimum_auc": round(float(effect.minimum_auc), 4),
                "power": effect.power,
                "summary": effect.summary,
            },
            "learning_curve": [
                {"n": int(n), "auc": round(float(a), 4)}
                for n, a in zip(curve.sizes, curve.scores, strict=True)
            ],
            "learning_slope": round(float(curve.slope), 4),
            "features": [
                {
                    "feature": name,
                    "r": round(float(row["r"]), 4),
                    "p": round(float(row["p"]), 4),
                    "threshold": round(float(row["bh_threshold"]), 4),
                    "reject": bool(row["reject"]),
                }
                for name, row in features.frame.iterrows()
            ],
            "expected_false_positives": round(
                float(features.expected_false_positives), 2
            ),
        },
    )


# --------------------------------------------------------------------------- #
# Cybersecurity threats
# --------------------------------------------------------------------------- #


def threats() -> None:
    """Structure tests first, then clusters judged against a null.

    The previous version drew a PCA scatter coloured by k-means cluster and by
    outlier flag -- a picture of exactly the kind the project now argues you
    cannot read without a null beside it. So the null is drawn beside it.
    """
    use("global-security-threats")

    from sklearn.decomposition import PCA
    from threat_structure.anomalies import detector_agreement, tail_checks
    from threat_structure.clustering import (
        compare_with_null,
        fit_kmeans,
        gap_statistic,
        stability,
    )
    from threat_structure.data import Incidents, load, shuffle_within_columns
    from threat_structure.structure import associations, balance, uniformity

    path = (
        DATA / "global-security-threats" / "data"
        / "Global_Cybersecurity_Threats_2015-2024.csv"
    )
    data = load(path)
    matrix = data.encoded()

    # Two projections side by side: the real data, and the same data with every
    # column independently shuffled. They look alike, which is the argument.
    shuffled = Incidents(frame=shuffle_within_columns(data.frame, seed=0))
    real_xy = PCA(n_components=2, random_state=SEED).fit_transform(matrix)
    null_xy = PCA(n_components=2, random_state=SEED).fit_transform(shuffled.encoded())
    labels = fit_kmeans(matrix, 4)
    null_labels = fit_kmeans(shuffled.encoded(), 4)

    null = compare_with_null(data, k=4, draws=40)
    firm = stability(data, k=4, draws=25)
    gap = gap_statistic(data, max_k=6, references=10)
    agreement = detector_agreement(data)

    uniform = uniformity(data)
    balanced = balance(data)
    linked = associations(data)
    pair, strength = linked.strongest_categorical

    # A thousand points per panel is plenty to see that the two clouds are the
    # same shape, and keeps the payload small enough to render as SVG.
    shown = np.random.default_rng(SEED).choice(len(matrix), 1000, replace=False)

    def points(xy, cluster) -> list[dict]:
        return [
            {
                "x": round(float(xy[i, 0]), 3),
                "y": round(float(xy[i, 1]), 3),
                "c": int(cluster[i]),
            }
            for i in shown
        ]

    write(
        "nb-threats.json",
        {
            "rows": len(data),
            "shown": len(shown),
            "columns": int(matrix.shape[1]),
            "projection": {
                "real": points(real_xy, labels),
                "shuffled": points(null_xy, null_labels),
            },
            "uniformity": [
                {
                    "column": name,
                    "d": round(float(row["D"]), 4),
                    "p": round(float(row["p"]), 4),
                }
                for name, row in uniform.frame.iterrows()
            ],
            "all_uniform": uniform.all_uniform,
            "balance": [
                {
                    "column": name,
                    "categories": int(row["categories"]),
                    "chi2": round(float(row["chi2"]), 2),
                    "p": round(float(row["p"]), 4),
                }
                for name, row in balanced.frame.iterrows()
            ],
            "balance_expected_false_positives": round(
                balanced.expected_false_positives, 2
            ),
            "balance_consistent_with_chance": balanced.consistent_with_chance,
            "strongest_association": {"pair": pair, "v": round(strength, 4)},
            "strongest_correlation": round(linked.strongest_numeric, 4),
            "independent": linked.independent,
            "silhouette": {
                "observed": round(null.observed, 4),
                "null_mean": round(null.null_mean, 4),
                "null_std": round(null.null_std, 4),
                "z": round(null.z_score, 3),
                "p": round(null.p_value, 4),
                "draws": len(null.null_scores),
                "better_than_noise": null.better_than_noise,
            },
            "stability": {
                "mean_ari": round(firm.mean_ari, 4),
                "low": round(firm.interval[0], 4),
                "high": round(firm.interval[1], 4),
                "stable": firm.stable,
            },
            "gap": [
                {
                    "k": int(k),
                    "gap": round(float(row["gap"]), 4),
                    "s_k": round(float(row["s_k"]), 4),
                }
                for k, row in gap.frame.iterrows()
            ],
            "best_k": gap.best_k,
            "says_no_clusters": gap.says_no_clusters,
            "agreement": {
                "flagged_a": agreement.flagged_a,
                "flagged_b": agreement.flagged_b,
                "overlap": agreement.overlap,
                "expected": round(agreement.expected_overlap, 1),
                "jaccard": round(agreement.jaccard, 3),
                "excess": round(agreement.excess, 2),
                "agree": agreement.agree,
            },
            "tails": [
                {
                    "column": check.column,
                    "percentile": round(check.flagged_mean_percentile, 3),
                    "just_a_tail": check.is_just_a_tail,
                }
                for check in tail_checks(data)
            ],
        },
    )


# --------------------------------------------------------------------------- #
# E-commerce recommendations
# --------------------------------------------------------------------------- #


def recommendations() -> None:
    """Ranking metrics from the package, not a descriptive bar chart.

    The previous version plotted customer segments and average spend, which
    are facts about the file rather than an evaluation of anything. Every
    cut-off the browser might offer is scored here so the slider is free.
    """
    use("personalized-recommendations-for-e-commerce")

    from rec_eval.data import browsing_leak, load_catalogue, load_customers
    from rec_eval.evaluate import leave_one_out
    from rec_eval.recommenders import (
        browsing_oracle,
        category_share_of_similar_lists,
        different_category,
        expected_category_share,
        popularity,
        probability_column_correlations,
        random_ranking,
        same_category,
        similar_products,
    )

    base = DATA / "personalized-recommendations-for-e-commerce" / "data"
    catalogue = load_catalogue(base / "product_recommendation_data.csv")
    customers = load_customers(base / "customer_data_collection.csv")

    recommenders = {
        "random": random_ranking(),
        "popularity": popularity(catalogue),
        "same category": same_category(catalogue),
        "different category": different_category(catalogue),
        "similar-product graph": similar_products(catalogue),
        "browsing (oracle)": browsing_oracle(catalogue),
    }

    cutoffs = (1, 3, 5, 10)
    by_k = {}
    evaluated = excluded = 0
    for k in cutoffs:
        result = leave_one_out(customers, catalogue, recommenders, k=k)
        evaluated, excluded = result.evaluated, result.excluded
        by_k[str(k)] = [
            {
                "name": score.name,
                "recall": round(score.recall, 4),
                "precision": round(score.precision, 4),
                "map": round(score.map_score, 4),
                "mrr": round(score.mrr, 4),
                "ndcg": round(score.ndcg, 4),
            }
            for score in result.scores
        ]

    leak = browsing_leak(customers, catalogue)
    correlations = probability_column_correlations(catalogue)

    write(
        "nb-recommend.json",
        {
            "customers": len(customers),
            "products": len(catalogue),
            "subcategories": len(catalogue.subcategories),
            "cutoffs": list(cutoffs),
            "evaluated": evaluated,
            "excluded": excluded,
            "by_k": by_k,
            "browsing_leak": round(leak.rate, 4),
            "browsing_deterministic": leak.is_deterministic,
            "similar_category_share": round(
                category_share_of_similar_lists(catalogue), 4
            ),
            "similar_category_chance": round(expected_category_share(catalogue), 4),
            # `dropna` because the CSV has two trailing empty columns, which
            # pandas names "Unnamed: 13/14" and which correlate with nothing
            # because they contain nothing. They are a file artefact, not a
            # feature, and a NaN is not valid JSON in any case.
            "probability_correlations": [
                {"feature": str(name), "r": round(float(value), 4)}
                for name, value in correlations.dropna().head(6).items()
            ],
            "popularity": [
                {"label": str(label), "count": int(count)}
                for label, count in catalogue.popularity().head(12).items()
            ],
        },
    )


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    print("extracting notebook results:")
    churn()
    fake_news()
    threats()
    recommendations()
    print("done")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
