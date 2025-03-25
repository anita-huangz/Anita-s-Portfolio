# 🌤️ Weather Trends and Forecast

## Project Overview 
This project enables users to download, analyze, and forecast weather patterns using historical weather data and basic machine learning. It integrates data retrieval via the Meteostat API, statistical summaries, and a simple forecasting model influenced by synthetic legislative factors. 

## Features 
1. **📥 Historical Data Collection**: Retrieves past weather data (temperature highs/lows) for any latitude and longitude using the Meteostat API.
2. **📊 Statistical Analysis**: Computes max, min, average, and standard deviation of temperatures across the dataset.
3. **📈 Forecasting with Policy Influence**: Predicts future maximum temperatures using linear regression and a dummy model for legislative impact.
4. **🖼️ Visualization**: Plots both historical and forecasted temperatures with customizable date axis formatting.
5. **📁 Modular Code**: Separated into download.py, stats.py, and forecast.py for clarity and reuse.

## Data Sources
1. **Meteostat API**: Used to retrieve historical weather observations. 

# Usage 
1. **Download Historical Weather Data**
```bash 
python3 download.py <latitude> <longitude> <days>
```
Outputs weather.json to the /data folder.

2. **Generate Weather Summary** 
```bash 
python3 stats.py
```
Generates Max/Min Temperatures, Averages and Standard Deviations, Start/End Dates

3. **Forecast Future Temperatures**
```bash 
python forecast.py
```
Plots Historical max temps, 30-day forecast influenced by legislative trends