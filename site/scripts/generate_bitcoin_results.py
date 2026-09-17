"""Bitcoin: run the saved LSTM on held-out days and compare to what happened."""
from __future__ import annotations
import json, os, pathlib, warnings
warnings.filterwarnings("ignore"); os.environ["TF_CPP_MIN_LOG_LEVEL"] = "3"
import numpy as np, pandas as pd, tensorflow as tf
from sklearn.preprocessing import MinMaxScaler

ROOT = pathlib.Path("data-science-projects/bitcoin-and-asset-trading")
OUT = pathlib.Path("site/src/data/demos")
LOOKBACK = 90          # taken from the saved model's input shape, not the README
TEST_FRACTION = 0.2

print("  reading 127 MB of minute trades…")
raw = pd.read_csv(ROOT / "data/btcusd_1-min_data.csv.zstd", compression="zstd")
ts = "Timestamp" if "Timestamp" in raw.columns else raw.columns[0]
raw[ts] = pd.to_datetime(raw[ts], unit="s", errors="coerce")
raw = raw.dropna(subset=[ts]).set_index(ts)

daily = raw["Close"].resample("D").last().dropna()
print(f"  {len(raw):,} minutes -> {len(daily):,} daily closes "
      f"({daily.index[0].date()} to {daily.index[-1].date()})")

values = daily.to_numpy(dtype="float32").reshape(-1, 1)
split = int(len(values) * (1 - TEST_FRACTION))

# The notebook saved the model but not the scaler, so it is refit here on the
# training portion only. Fitting on the whole series would leak the test range
# into the transform -- the same class of mistake the factor project fixed.
def build(scaler_fit_on_all: bool):
    """Two scalings, deliberately. Fitting MinMax on the whole series before
    splitting is the classic leak in a price pipeline: the transform already
    knows the test range's maximum. Fitting on train only is correct, and on
    an asset that tripled after the split it means the model is asked to
    extrapolate far outside anything it saw."""
    sc = MinMaxScaler().fit(values if scaler_fit_on_all else values[:split])
    return sc, sc.transform(values)


scaler, scaled = build(scaler_fit_on_all=False)

X, y, idx = [], [], []
for i in range(LOOKBACK, len(scaled)):
    X.append(scaled[i - LOOKBACK : i, 0])
    y.append(scaled[i, 0])
    idx.append(i)
X = np.array(X)[..., None]
y = np.array(y)
idx = np.array(idx)

test_mask = idx >= split
model = tf.keras.models.load_model(ROOT / "notebooks/bitcoin_lstm_model.h5", compile=False)
pred_scaled = model.predict(X[test_mask], verbose=0)

actual = scaler.inverse_transform(y[test_mask].reshape(-1, 1)).ravel()
predicted = scaler.inverse_transform(pred_scaled).ravel()
dates = daily.index[idx[test_mask]]

err = predicted - actual
rmse = float(np.sqrt((err**2).mean()))
mae = float(np.abs(err).mean())
mape = float((np.abs(err) / actual).mean() * 100)

# The comparison that matters for a price model: a naive "tomorrow equals
# today" forecast. Beating it is the bar; matching it means the model has
# learned the level and not the change.
naive = scaler.inverse_transform(X[test_mask][:, -1, :]).ravel()
naive_rmse = float(np.sqrt(((naive - actual) ** 2).mean()))

# Directional accuracy: did it get the sign of the daily move right?
prev = naive
direction = float(((predicted > prev) == (actual > prev)).mean() * 100)

# Now the leaky variant, for comparison.
leak_scaler, leak_scaled = build(scaler_fit_on_all=True)
lX = np.array([leak_scaled[i - LOOKBACK : i, 0] for i in idx])[..., None]
ly = np.array([leak_scaled[i, 0] for i in idx])
leak_pred = leak_scaler.inverse_transform(model.predict(lX[test_mask], verbose=0)).ravel()
leak_actual = leak_scaler.inverse_transform(ly[test_mask].reshape(-1, 1)).ravel()
leak_rmse = float(np.sqrt(((leak_pred - leak_actual) ** 2).mean()))
leak_mape = float((np.abs(leak_pred - leak_actual) / leak_actual).mean() * 100)
leak_dir = float(((leak_pred > naive) == (leak_actual > naive)).mean() * 100)
print(f"  leaky scaling: RMSE ${leak_rmse:,.0f}  MAPE {leak_mape:.2f}%  "
      f"direction {leak_dir:.1f}%")

step = max(1, len(actual) // 400)
payload = {
    "source": "Kaggle: mczielinski/bitcoin-historical-data (minute trades, resampled daily)",
    "lookback": LOOKBACK,
    "model": "2-layer LSTM (100, 50) with dropout, dense 25 -> 1; 72,301 parameters",
    "train_days": int(split), "test_days": int(test_mask.sum()),
    "first_date": str(daily.index[0].date()), "last_date": str(daily.index[-1].date()),
    "metrics": {
        "rmse": round(rmse, 2), "mae": round(mae, 2), "mape": round(mape, 3),
        "naive_rmse": round(naive_rmse, 2),
        "directional_accuracy": round(direction, 2),
    },
    "leaky_metrics": {
        "rmse": round(leak_rmse, 2),
        "mape": round(leak_mape, 3),
        "directional_accuracy": round(leak_dir, 2),
    },
    "train_max": round(float(values[:split].max()), 2),
    "test_max": round(float(values[split:].max()), 2),
    "series": [
        {"date": str(d.date()), "actual": round(float(a), 2),
         "predicted": round(float(p), 2), "naive": round(float(n), 2),
         "leaky": round(float(l), 2)}
        for d, a, p, n, l in list(zip(dates, actual, predicted, naive, leak_pred))[::step]
    ],
}
path = OUT / "nb-bitcoin.json"
path.write_text(json.dumps(payload, separators=(",", ":")) + "\n")
print(f"  RMSE ${rmse:,.0f} vs naive ${naive_rmse:,.0f}  |  MAPE {mape:.2f}%  |  "
      f"direction {direction:.1f}%")
print(f"  nb-bitcoin.json  {path.stat().st_size/1024:.1f} KB")
