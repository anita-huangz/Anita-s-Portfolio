# 📊 Earnings Drift Tracker

This project analyzes how stock prices react to earnings announcements, using real-time earnings data from the Financial Modeling Prep (FMP) API and historical price data from Yahoo Finance.

---

## 🚀 Features

- Fetches the last 12 earnings reports for a given stock
- Calculates earnings surprise (%)
- Measures post-earnings price drift (1-day, 5-day, and 10-day)
- Generates summary reports and a scatter plot visualization


---

## 🔑 Requirements

- Python 3.7+
- Libraries: `requests`, `yfinance`, `pandas`, `matplotlib`
- [Financial Modeling Prep API Key](https://financialmodelingprep.com/developer/docs)

---

## 📦 Installation

```bash
pip install requests yfinance pandas matplotlib
```

---

## 🔧 Setup 
```bash
API_KEY = "your_api_key_here"

python main.py
``` 