## 📦 Dataset Overview

- **Source**: KaggleHub Dataset: `khushikyad001/fake-news-detection`
- **Size**: 4,000 articles
- **Features**:
  - Text: `title`, `text`
  - Metadata: `source`, `category`, `state`, `date_published`, `author`
  - Numerical: `sentiment_score`, `clickbait_score`, `trust_score`, etc.
  - Labels: `Fake` or `Real`

---

## 🧹 Preprocessing Steps

Goal: Convert raw data into a model-ready format (256 features).

- **Drop ID**: Irrelevant for modeling.
- **TF-IDF**: Extracted top 100 features each from `title` and `text`.
- **One-Hot Encoding**: Categorical columns (`source`, `state`, etc.).
- **Date Parsing**: `days_since` earliest publish date.
- **Standardization**: Normalized numerical features.
- **Label Encoding**: `Fake` = 1, `Real` = 0.

✅ Shape: `(4000, 256)`

---

## 🔧 Feature Engineering

Goal: Enhance predictive power beyond raw TF-IDF and metadata.

Engineered 12 additional features:

| Feature | Why It Was Added |
|--------|------------------|
| `title_length` | Captures wordiness or minimalism (clickbait proxy) |
| `text_sentiment_consistency` | Detects mismatched tone vs. overall sentiment |
| `engagement_ratio` | Measures virality: shares vs. comments |
| `credibility_composite` | Blends trust_score & source_reputation |
| `title_entropy` | Assesses lexical diversity in title |
| `text_entropy` | Assesses lexical diversity in body |
| `readability_squared` | Captures complexity through squared readability |
| `readability_inverse` | Highlights extreme difficulty/ease to read |
| `shares_to_length` | Share efficiency relative to article length |
| `media_richness` | Encodes presence of image/video media |
| `clickbait_vs_credibility` | Interaction of emotional tone & reputation |

✅ Final Shape: `(4000, 268)`

---

## 📊 EDA Highlights

- **Balanced Labels**: 50.65% Fake, 49.35% Real
- **Numerical Signals**: Most features overlapped between labels
- **Categorical Trends**:
  - `Entertainment` category: 54% Fake
  - `BBC`: 57.5% Fake
  - `Maryland`: 58.6% Fake
  - `CNN`: 52.9% Real
- **Correlation**: Near-zero correlation between most numeric features
- **Top Engineered Feature Signals**:
  - `credibility_composite`: Best separation
  - Others (e.g., `title_length`, `entropy`) weakly separated

---

## 🤖 Model Selection & Evaluation

### 🧪 Experiment Setup
- **Train/Test Split**: 80/20
- **Feature Reduction**: Top 50 via Random Forest importance

### 🧠 Models Used
| Model | Rationale |
|-------|-----------|
| Logistic Regression | Simple, baseline for high-dimensional data |
| Random Forest | Captures non-linear interactions |
| XGBoost | Boosting with regularization |
| SVM | Handles small/mid datasets well |
| Gradient Boosting | Sequential tree ensemble |
| MLP (Neural Net) | Explores deep learning baseline |

### 🔍 Results Summary
📌 **Top Features (by importance)**:
- `engagement_ratio`, `clickbait_vs_credibility`, `shares_to_length`, `credibility_composite`

---

## ❗ Challenges & Learnings

### ❌ Why Performance Plateaued (48%–53%)
- **Feature Overlap**: Fake and Real distributions look nearly identical for most features.
- **Sparse TF-IDF**: Generic and high-dimensional—fails to capture tone shifts or satire.
- **Small Dataset**: 4,000 samples and 268 features = overfitting risk.
- **Metadata Noise**: Inconsistent label quality (e.g., BBC marked Fake).
- **Model Underfit**: Even advanced models failed to leverage weak signals.

---

## 🔮 Future Improvements

- 🔁 Use **BERT/RoBERTa** embeddings instead of TF-IDF
- 🧠 Include **n-grams**, **POS tags**, or **topic modeling**
- 🧼 Improve label quality and text preprocessing
- 🔍 Explore multi-task learning (e.g., classify satire vs. fake)
- 📈 Expand dataset size for better generalization

---

## ✅ Final Takeaway
Despite extensive feature engineering, modeling, and tuning, results stayed close to chance. This highlights a key lesson in machine learning: **data quality and representation often matter more than model complexity**.

Thanks for reading! Contributions and feedback welcome 🙌