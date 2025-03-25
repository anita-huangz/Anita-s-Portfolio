import json
import datetime
import numpy as np
from sklearn.linear_model import LinearRegression
import matplotlib.pyplot as plt
import os  # Needed for path joining


def load_weather_data(filename=None):
    if filename is None:
        # Dynamically resolve the path to data/weather.json relative to the script
        base_dir = os.path.dirname(__file__)
        filename = os.path.join(base_dir, "..", "data", "weather.json")
        filename = os.path.abspath(filename)  # Get absolute path

    with open(filename, "r", encoding='utf-8') as file:
        weather_data = json.load(file)

    return weather_data["daily"]


def generate_dummy_legislation_influence(dates):
    """
    Dummy model: returns an influence factor based on synthetic 'policy strength'.
    For real use, replace with actual legislative data aligned with dates.
    """
    influence = []
    for date in dates:
        year = int(date[:4])
        # Example: after 2020, pretend stronger green policies kick in
        influence.append(1.0 if year < 2020 else 0.8)
    return np.array(influence)


def prepare_features(dates, policy_influence):
    """
    Convert dates to ordinal and combine with policy influence as features.
    """
    ordinals = [datetime.date.fromisoformat(d).toordinal() for d in dates]
    X = np.column_stack((ordinals, policy_influence))
    return X


def run_forecast(weather_data):
    dates = weather_data["time"]
    max_temps = weather_data["temperature_2m_max"]

    # Filter out None values
    filtered = [(d, t) for d, t in zip(dates, max_temps) if t is not None]
    dates, temps = zip(*filtered)

    # Dummy legislative influence values (real-world: use actual data)
    policy_influence = generate_dummy_legislation_influence(dates)

    # Prepare features (date + legislative influence)
    X = prepare_features(dates, policy_influence)
    y = np.array(temps)

    # Train the model
    model = LinearRegression()
    model.fit(X, y)

    # Forecast 30 days into the future
    last_date = datetime.date.fromisoformat(dates[-1])
    future_dates = [last_date + datetime.timedelta(days=i) for i in range(1, 31)]
    future_date_strs = [d.isoformat() for d in future_dates]

    future_policy = generate_dummy_legislation_influence(future_date_strs)
    X_future = prepare_features(future_date_strs, future_policy)
    predictions = model.predict(X_future)

    # Plotting
    plt.figure(figsize=(12, 5))
    plt.plot(dates, temps, label="Historical Max Temp")
    plt.plot(future_date_strs, predictions, label="Forecasted Max Temp", linestyle="--")

    all_dates = list(dates) + future_date_strs
    tick_indices = list(range(0, len(all_dates), 7))
    tick_labels = [all_dates[i] for i in tick_indices]
    plt.xticks(ticks=tick_indices, labels=tick_labels, rotation=45)

    plt.xlabel("Date")
    plt.ylabel("Temperature (°C)")
    plt.title("Forecasted Max Temperature with Legislative Influence")
    plt.legend()
    plt.tight_layout()
    plt.show()



if __name__ == "__main__":
    weather_data = load_weather_data()
    run_forecast(weather_data)
