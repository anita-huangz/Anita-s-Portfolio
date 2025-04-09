import pandas as pd
import numpy as np
import yfinance as yf
from yahooquery import Ticker
import pandas_datareader.data as web

def download_price_data(tickers, start_date, end_date):
    """
    Uses yfinance to download adjusted close prices for tickers.
    Purpose: Pulls historical closing prices using the yfinance API.
    """
    return yf.download(tickers, start=start_date, end=end_date)['Close']


def get_pe_marketcap(tickers):
    """
    Fetches PE ratio and market cap for a list of tickers using yahooquery.
    Returns two dictionaries: pe_ratios and market_caps
    """
    t = Ticker(tickers)
    pe_ratios = {}
    market_caps = {}

    for ticker in tickers:
        summary = t.summary_detail.get(ticker, {})
        pe = summary.get('trailingPE', None)
        market_cap = summary.get('marketCap', None)

        pe_ratios[ticker] = pe if pe is not None else np.nan
        market_caps[ticker] = market_cap if market_cap is not None else np.nan

    return pe_ratios, market_caps


def calculate_factor_data(price_data, selected_factors):
    """
    Dynamically calculates only the selected factors based on user input.
    Returns a DataFrame where each row is a ticker and columns are selected factors.
    """
    factor_data = {}

    if '12M_Return' in selected_factors:
        # Calculates actual 1-year return using real historical price data from Yahoo Finance. 
        factor_data['12M_Return'] = price_data.pct_change(252).iloc[-1]

    if 'Volatility' in selected_factors:
        # Computes annualized volatility from historical daily price changes (21-day rolling window).
        daily_vol = price_data.pct_change().rolling(21).std().iloc[-1]
        factor_data['Volatility'] = daily_vol * np.sqrt(252)

    if 'PE' in selected_factors or 'MarketCap' in selected_factors:
        pe_ratios, market_caps = get_pe_marketcap(price_data.columns)

        if 'PE' in selected_factors:
            factor_data['PE'] = pd.Series(pe_ratios)

        if 'MarketCap' in selected_factors:
            factor_data['MarketCap'] = pd.Series(market_caps)

    return pd.DataFrame(factor_data)


def load_fama_french_factors():
    try:
        ff = web.DataReader('F-F_Research_Data_Factors_daily', 'famafrench')[0]
        ff.index = pd.to_datetime(ff.index, format="%Y%m%d")
        ff = ff.rename(columns=lambda x: x.strip())  # remove trailing spaces
        print("\n✅ Fama-French Data Sample:\n", ff.head())  # ✅ Add this line
        return ff / 100  # convert % to decimal
    except Exception as e:
        print("❌ Failed to load Fama-French data:", e)
        return pd.DataFrame()
