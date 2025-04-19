import requests
import yfinance as yf
from earnings import EarningsReport

API_KEY = "2Wxxo8fva4htYsD1j3LLU9Z1hi6AyWtS"  # FMP API Key

def load_price_data(ticker, start, end):
    # Use yfinance to download historical stock prices
    return yf.download(ticker, start=start, end=end)

def load_earnings(ticker):
    # Fetch latest earnings from FMP
    url = f"https://financialmodelingprep.com/api/v3/earnings-surprises/{ticker}?limit=12&apikey={API_KEY}"
    response = requests.get(url)
    data = response.json()
    reports = []
    for item in data:
        if item.get("actualEarningResult") is not None and item.get("estimatedEarning") is not None:
            report = EarningsReport(
                date=item["date"],
                eps_actual=item["actualEarningResult"],
                eps_estimate=item["estimatedEarning"]
            )
            reports.append(report)
    return reports
