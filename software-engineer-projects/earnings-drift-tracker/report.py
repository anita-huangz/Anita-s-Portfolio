import matplotlib.pyplot as plt
import pandas as pd

# Print summary table and statistics

def show_drift_summary(drift_df):
    numeric_cols = ["1d", "5d", "10d"]
    drift_df[numeric_cols] = drift_df[numeric_cols].apply(pd.to_numeric, errors='coerce')
    print(drift_df[["date", "surprise_pct", "1d", "5d", "10d"]])
    avg = drift_df[numeric_cols].mean()
    print("\nAverage Post-Earnings Drifts:")
    print(avg)

# Plot surprise % vs post-earnings returns

def plot_drift(drift_df):
    plt.scatter(drift_df["surprise_pct"], drift_df["1d"], label="1D Drift")
    plt.scatter(drift_df["surprise_pct"], drift_df["5d"], label="5D Drift")
    plt.scatter(drift_df["surprise_pct"], drift_df["10d"], label="10D Drift")
    plt.axhline(0, color='gray', linestyle='--')
    plt.xlabel("Earnings Surprise (%)")
    plt.ylabel("Post-Earnings Return")
    plt.title("Earnings Surprise vs Post-Earnings Drift")
    plt.legend()
    plt.grid(True)
    plt.show()
