import sys
import datetime
import urllib.request


def save_json(lat, lng, days):
    """
    Make a request to open-meteo.com's weather API for the last
    {days} days of weather information at the given location.

    Writes a file named "weather.json" containing the historical weather
    information.

    Parameters:
        lat: float  : latitude of location
        lng: float  : longitude of location
        days: int   : number of days in past to request
    """

    # 1. Get today's date for end_date
    end_date = datetime.date.today()

    # 2. Calculate start_date using datetime.timedelta
    start_date = end_date - datetime.timedelta(days=days)

    # 3 & 4. Construct the API URL and make a request using urllib.request
    url = f"https://archive-api.open-meteo.com/v1/era5?latitude={lat}&longitude={lng}" \
          f"&start_date={start_date}&end_date={end_date}" \
          "&daily=temperature_2m_max,temperature_2m_min&timezone=auto"

    with urllib.request.urlopen(url) as response:
        data = response.read()  # Read the response content

    # 5. Save the result of reading the response to "weather.json"
    # Inspired by:
        #  https://stackoverflow.com/questions/60097340/
        #       jupyter-notebook-with-openpath-wb-as-file-then-write-results-in-unicode
    with open("weather.json", "wb") as file:
        file.write(data)  # Write data to file


if __name__ == "__main__":
    if len(sys.argv) != 4:
        print("Usage: download.py <lat> <lng> <days>")
    else:
        save_json(float(sys.argv[1]), float(sys.argv[2]), int(sys.argv[3]))
