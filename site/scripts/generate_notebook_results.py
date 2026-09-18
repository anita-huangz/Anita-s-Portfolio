"""Extract chartable results from the data-science projects.

The notebooks are analyses, not libraries: there is no importable function to
call, so this re-runs their core computation against the same CSVs and writes
structured JSON the site can plot. Each section is deliberately a faithful,
small version of what the notebook does -- enough to produce an honest chart,
not a reimplementation of the whole analysis.

Everything is seeded. A chart that changes between runs is not a result.

    python site/scripts/generate_notebook_results.py
"""

from __future__ import annotations

import json
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")

SEED = 42
ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data-science-projects"
OUT = ROOT / "site" / "src" / "data" / "demos"


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
    import sys

    sys.path.insert(0, str(DATA / "customer-churn-prediction" / "src"))

    from sklearn.metrics import confusion_matrix, roc_auc_score

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
            "rows": int(len(data)),
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
    from sklearn.ensemble import RandomForestClassifier
    from sklearn.metrics import confusion_matrix, roc_auc_score
    from sklearn.model_selection import train_test_split

    df = pd.read_csv(DATA / "fake-news-detection/data/fake_news_dataset.csv")
    label_col = next(
        (c for c in df.columns if c.lower() in {"label", "is_fake", "fake", "target"}),
        None,
    )
    if label_col is None:
        print("  fake news: no label column; skipped")
        return

    labels = df[label_col]
    # pandas 3 gives text columns a `str` dtype rather than `object`, so
    # checking for `object` silently misclassified them as numeric.
    y = (
        labels.astype(int)
        if pd.api.types.is_numeric_dtype(labels)
        else labels.astype(str).str.strip().str.lower().isin({"fake", "1", "true"}).astype(int)
    )

    # Metadata features only -- the notebook's point is how much signal sits in
    # article metadata before any text modelling.
    numeric = ["sentiment_score", "word_count", "char_count", "readability_score"]
    flags = ["has_images", "has_videos"]
    usable = [c for c in numeric + flags if c in df.columns]
    X = df[usable].apply(pd.to_numeric, errors="coerce").fillna(0)
    for col in ["category", "source", "state"]:
        if col in df.columns:
            X = pd.concat([X, pd.get_dummies(df[col], prefix=col, drop_first=True)], axis=1)

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=SEED, stratify=y
    )
    model = RandomForestClassifier(
        n_estimators=300, min_samples_leaf=3, random_state=SEED, n_jobs=-1
    ).fit(X_train, y_train)

    proba = model.predict_proba(X_test)[:, 1]
    predicted = (proba >= 0.5).astype(int)
    tn, fp, fn, tp = confusion_matrix(y_test, predicted).ravel()
    importances = (
        pd.Series(model.feature_importances_, index=X.columns)
        .sort_values(ascending=False)
        .head(12)
    )

    # Real articles from the test split, with the model's score next to the
    # truth. An aggregate metric answers "how good"; only an example answers
    # "what am I actually looking at".
    test_rows = df.loc[X_test.index]
    sample = []
    rng = np.random.default_rng(SEED)
    order = rng.permutation(len(test_rows))
    for i in order[:60]:
        row = test_rows.iloc[int(i)]
        score = float(proba[int(i)])
        sample.append(
            {
                "title": str(row.get("title", ""))[:180],
                "author": str(row.get("author", "")),
                "source": str(row.get("source", "")),
                "category": str(row.get("category", "")),
                "date": str(row.get("date_published", ""))[:10],
                "excerpt": " ".join(str(row.get("text", "")).split())[:320],
                "words": int(row.get("word_count", 0) or 0),
                "readability": round(float(row.get("readability_score", 0) or 0), 1),
                "sentiment": round(float(row.get("sentiment_score", 0) or 0), 3),
                "actual": "fake" if int(y_test.iloc[int(i)]) == 1 else "real",
                "predicted": "fake" if score >= 0.5 else "real",
                "score": round(score, 4),
            }
        )

    # Diagnosis. An AUC at chance has two possible causes: the features are
    # uninformative, or the labels are. Distinguishing them matters, and the
    # evidence below points squarely at the second.
    feature_corr = [
        {"feature": c, "corr": round(float(df[c].corr(y)), 4)}
        for c in numeric + flags
        if c in df.columns
    ]
    rate_by = {}
    for col in ["source", "category", "author"]:
        if col in df.columns:
            rate_by[col] = [
                {"label": str(k), "rate": round(float(v), 4), "n": int((df[col] == k).sum())}
                for k, v in y.groupby(df[col]).mean().sort_values(ascending=False).items()
            ]

    write(
        "nb-fakenews.json",
        {
            "rows": int(len(df)),
            "sample": sample,
            "feature_corr": feature_corr,
            "rate_by": rate_by,
            "distinct_titles": int(df["title"].nunique()) if "title" in df else None,
            "distinct_texts": int(df["text"].nunique()) if "text" in df else None,
            "fake_rate": round(float(y.mean()), 4),
            "auc": round(float(roc_auc_score(y_test, proba)), 4),
            "accuracy": round(float((predicted == y_test).mean()), 4),
            "confusion": {"tn": int(tn), "fp": int(fp), "fn": int(fn), "tp": int(tp)},
            "roc": roc_points(y_test, proba),
            # Per-row scores, so the threshold can be moved in the browser
            # rather than being frozen at whatever 0.5 happened to give.
            "scores": [
                {"p": round(float(pr), 4), "y": int(t)}
                for pr, t in zip(proba, y_test, strict=True)
            ],
            "importances": [
                {"feature": f, "weight": round(float(w), 5)}
                for f, w in importances.items()
            ],
        },
    )


# --------------------------------------------------------------------------- #
# Cybersecurity threats
# --------------------------------------------------------------------------- #


def threats() -> None:
    from sklearn.cluster import KMeans
    from sklearn.decomposition import PCA
    from sklearn.ensemble import IsolationForest
    from sklearn.preprocessing import StandardScaler

    df = pd.read_csv(
        DATA / "global-security-threats/data/Global_Cybersecurity_Threats_2015-2024.csv"
    )
    numeric = [
        "Financial Loss (in Million $)",
        "Number of Affected Users",
        "Incident Resolution Time (in Hours)",
        "Year",
    ]
    X = StandardScaler().fit_transform(df[numeric].fillna(df[numeric].median()))

    coords = PCA(n_components=2, random_state=SEED).fit_transform(X)
    clusters = KMeans(n_clusters=4, random_state=SEED, n_init=10).fit_predict(X)
    outlier = IsolationForest(contamination=0.05, random_state=SEED).fit_predict(X) == -1

    by_type = df["Attack Type"].value_counts()
    loss_by_industry = (
        df.groupby("Target Industry")["Financial Loss (in Million $)"]
        .mean()
        .sort_values(ascending=False)
    )
    by_year = df.groupby("Year").size()

    write(
        "nb-threats.json",
        {
            "rows": int(len(df)),
            "years": [int(df["Year"].min()), int(df["Year"].max())],
            "points": [
                {
                    "x": round(float(coords[i, 0]), 3),
                    "y": round(float(coords[i, 1]), 3),
                    "c": int(clusters[i]),
                    "o": bool(outlier[i]),
                    "t": df["Attack Type"].iloc[i],
                    "i": df["Target Industry"].iloc[i],
                    "yr": int(df["Year"].iloc[i]),
                    "loss": round(float(df["Financial Loss (in Million $)"].iloc[i]), 2),
                }
                for i in range(len(df))
            ],
            "by_type": [{"label": k, "count": int(v)} for k, v in by_type.items()],
            "loss_by_industry": [
                {"label": k, "value": round(float(v), 2)}
                for k, v in loss_by_industry.items()
            ],
            "by_year": [{"year": int(k), "count": int(v)} for k, v in by_year.items()],
            "industries": sorted(df["Target Industry"].dropna().unique().tolist()),
            "attack_types": sorted(df["Attack Type"].dropna().unique().tolist()),
            "outlier_count": int(outlier.sum()),
        },
    )


# --------------------------------------------------------------------------- #
# E-commerce recommendations
# --------------------------------------------------------------------------- #


def recommendations() -> None:
    customers = pd.read_csv(
        DATA / "personalized-recommendations-for-e-commerce/data/customer_data_collection.csv"
    )
    products = pd.read_csv(
        DATA / "personalized-recommendations-for-e-commerce/data/product_recommendation_data.csv"
    )

    segment = customers["Customer_Segment"].value_counts()
    by_category = (
        products.groupby("Category")
        .agg(count=("Product_ID", "size"), rating=("Product_Rating", "mean"),
             price=("Price", "mean"))
        .sort_values("count", ascending=False)
    )
    spend_by_segment = customers.groupby("Customer_Segment")["Avg_Order_Value"].mean()

    # Per-segment category interest, so the demo can ask whether the segments
    # actually behave differently -- the premise a recommender rests on.
    interest = {}
    if "Browsing_History" in customers.columns:
        for segment_name, group in customers.groupby("Customer_Segment"):
            counts: dict[str, int] = {}
            for entry in group["Browsing_History"].dropna().astype(str):
                for item in entry.strip("[]").replace("'", "").split(","):
                    key = item.strip()
                    if key:
                        counts[key] = counts.get(key, 0) + 1
            total = sum(counts.values()) or 1
            interest[str(segment_name)] = [
                {"label": k, "share": round(v / total, 4)}
                for k, v in sorted(counts.items(), key=lambda kv: -kv[1])[:8]
            ]

    write(
        "nb-recommend.json",
        {
            "customers": int(len(customers)),
            "products": int(len(products)),
            "segments": [{"label": k, "count": int(v)} for k, v in segment.items()],
            "by_category": [
                {
                    "label": k,
                    "count": int(v["count"]),
                    "rating": round(float(v["rating"]), 2),
                    "price": round(float(v["price"]), 2),
                }
                for k, v in by_category.iterrows()
            ],
            "spend_by_segment": [
                {"label": k, "value": round(float(v), 2)}
                for k, v in spend_by_segment.items()
            ],
            "interest_by_segment": interest,
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
