import json
import statistics
import os  # Needed for path joining


def summarize_weather(filename=None):
    """
    Reads weather data from a JSON file and summarizes it.
    """
    # If no filename is provided, use the default data path
    if filename is None:
        # Dynamically resolve the path to data/weather.json relative to the script
        base_dir = os.path.dirname(__file__)
        filename = os.path.join(base_dir, "..", "data", "weather.json")
        filename = os.path.abspath(filename)  # Get absolute path

    with open(filename, "r", encoding='utf-8') as file:
        weather_data = json.load(file)

    daily_data = weather_data["daily"]
    max_temps = list(filter(lambda temp: temp is not None, daily_data["temperature_2m_max"]))
    min_temps = list(filter(lambda temp: temp is not None, daily_data["temperature_2m_min"]))

    summary = {
        "start_date": daily_data["time"][0],
        "end_date": daily_data["time"][-1],
        "max_high": max(max_temps),
        "min_low": min(min_temps),
        "mean_high": statistics.mean(max_temps),
        "mean_low": statistics.mean(min_temps),
        "std_dev_high": statistics.stdev(max_temps),
        "std_dev_low": statistics.stdev(min_temps)
    }

    return summary

def main():
    """
    Reads in weather data from weather.json and prints out a summary.
    """
    summary = summarize_weather()
    print(
        """       Weather Report
===========================
{start_date}       {end_date}
===========================
High Temperature:   {max_high:>6.1f}
     Average:       {mean_high:>6.1f}
     Std. Dev:      {std_dev_high:>6.1f}
Low Temperature:    {min_low:>6.1f}
     Average:       {mean_low:>6.1f}
     Std. Dev:      {std_dev_low:>6.1f}
          """.format(**summary)
    )


if __name__ == "__main__":
    main()
