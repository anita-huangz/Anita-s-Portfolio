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
    from sklearn.ensemble import RandomForestClassifier
    from sklearn.metrics import confusion_matrix, roc_auc_score
    from sklearn.model_selection import train_test_split

    df = pd.read_csv(DATA / "customer-churn-prediction/data/telco-customer-churn.csv")
    df["TotalCharges"] = pd.to_numeric(df["TotalCharges"], errors="coerce")
    df = df.dropna(subset=["TotalCharges"])

    y = (df["Churn"] == "Yes").astype(int)
    features = df.drop(columns=["customerID", "Churn"])
    X = pd.get_dummies(features, drop_first=True)

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

    # Churn rate by contract type: the single clearest driver in this dataset.
    by_contract = (
        df.assign(churn=y)
        .groupby("Contract")["churn"]
        .agg(["mean", "size"])
        .sort_values("mean", ascending=False)
    )

    write(
        "nb-churn.json",
        {
            "rows": int(len(df)),
            "churn_rate": round(float(y.mean()), 4),
            "auc": round(float(roc_auc_score(y_test, proba)), 4),
            "accuracy": round(float((predicted == y_test).mean()), 4),
            "precision": round(float(tp / (tp + fp)), 4),
            "recall": round(float(tp / (tp + fn)), 4),
            "confusion": {"tn": int(tn), "fp": int(fp), "fn": int(fn), "tp": int(tp)},
            "roc": roc_points(y_test, proba),
            "importances": [
                {"feature": f, "weight": round(float(w), 5)}
                for f, w in importances.items()
            ],
            "by_contract": [
                {"label": k, "rate": round(float(v["mean"]), 4), "count": int(v["size"])}
                for k, v in by_contract.iterrows()
            ],
        },
    )


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

    write(
        "nb-fakenews.json",
        {
            "rows": int(len(df)),
            "fake_rate": round(float(y.mean()), 4),
            "auc": round(float(roc_auc_score(y_test, proba)), 4),
            "accuracy": round(float((predicted == y_test).mean()), 4),
            "confusion": {"tn": int(tn), "fp": int(fp), "fn": int(fn), "tp": int(tp)},
            "roc": roc_points(y_test, proba),
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
                }
                for i in range(len(df))
            ],
            "by_type": [{"label": k, "count": int(v)} for k, v in by_type.items()],
            "loss_by_industry": [
                {"label": k, "value": round(float(v), 2)}
                for k, v in loss_by_industry.items()
            ],
            "by_year": [{"year": int(k), "count": int(v)} for k, v in by_year.items()],
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
