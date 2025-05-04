# drift_analyzer.py
import pandas as pd

class DriftAnalyzer:
    def __init__(self, stock):
        self.stock = stock
        self.drifts = []  # stores all drift calculations

    def analyze(self):
        price_df = self.stock.price_data
        price_df = price_df.sort_index()  # ensure sorted index

        for report in self.stock.earnings:
            date = report.date
            print(f"Checking earnings report on {date.date()}...")

            if date not in price_df.index:
                print(f"[SKIP] {date.date()} not in price index")
                continue

            try:
                idx = price_df.index.get_loc(date)

                p0 = price_df['Close'].iloc[idx].item()
                p1 = price_df['Close'].iloc[idx + 1].item()
                p5 = price_df['Close'].iloc[idx + 5].item()
                p10 = price_df['Close'].iloc[idx + 10].item()

                print(f"[OK] Prices on {date.date()} → p0={p0}, p1={p1}, p5={p5}, p10={p10}")

                drift = {
                    "date": date,
                    "surprise_pct": report.surprise_pct(),
                    "1d": (p1 / p0) - 1,
                    "5d": (p5 / p0) - 1,
                    "10d": (p10 / p0) - 1
                }
                self.drifts.append(drift)

            except IndexError as e:
                print(f"[SKIP] Not enough price data after {date.date()}: {e}")
            except Exception as e:
                print(f"[ERROR] Unexpected error at {date.date()}: {e}")

    def get_drift_df(self):
        return pd.DataFrame(self.drifts)
