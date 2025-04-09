import pandas as pd
import numpy as np
import yfinance as yf
import matplotlib.pyplot as plt
from yahooquery import Ticker
import statsmodels.api as sm

# -------------------- #
# 1. Define Core Class # 
# -------------------- #

class Security:
    """
    Represents a single stock/security with historical price and factor exposures.
    Purpose: Encapsulates all data related to a single stock, including its prices and factor metrics. 
    """
    def __init__(self, ticker, prices, factor_exposures):
        self.ticker = ticker
        self.prices = prices  # pd.Series of daily close prices
        self.factor_exposures = factor_exposures  # Dict of factor name to value


# 🧠 FactorModel base class
class FactorModel:
    """
    Abstract base class for a factor model.
    Purpose: Base class that defines the interface for factor models. It enforces a .score() method.
    """
    def score(self, security):
        raise NotImplementedError


# 📈 Concrete Factor Models
class ValueFactor(FactorModel):
    """
    Purpose: Implements a Value investing factor where lower PE means better value (inverse of PE is used).
    """
    def score(self, security):
        # Higher score = better value (lower PE)
        return 1 / security.factor_exposures['PE']


class MomentumFactor(FactorModel):
    """
    Purpose: Implements a Momentum factor using 12-month return.
    """
    def score(self, security):
        return security.factor_exposures['12M_Return']


class SizeFactor(FactorModel):
    def score(self, security):
        return -security.factor_exposures['MarketCap']  # Smaller is better


class LowVolatilityFactor(FactorModel):
    def score(self, security):
        return -security.factor_exposures['Volatility']  # Lower vol is better
    

# 🔹 Portfolio Construction
class RankBasedOptimizer:
    """
    Ranks securities by score and selects top N with equal weight.
    Purpose: Simple portfolio construction method. Ranks stocks and selects the top N with equal weighting.
    """
    def __init__(self, top_n=3):
        self.top_n = top_n

    def optimize(self, scores):
        top = sorted(scores, key=scores.get, reverse=True)[:self.top_n]
        return {ticker: 1/self.top_n for ticker in top}


class Portfolio:
    """
    Tracks cash and holdings, handles rebalancing and valuation.
    Purpose: Simulates portfolio logic: allocation, value computation, and NAV tracking.
    """
    def __init__(self, initial_cash):
        self.cash = initial_cash
        self.holdings = {}  # Ticker to number of shares
        self.history = []   # List of (date, nav)

    def rebalance(self, weights, prices):
        total_value = self.cash + sum(prices[t] * self.holdings.get(t, 0) for t in weights)
        self.holdings = {t: (weights[t] * total_value) / prices[t] for t in weights}
        self.cash = 0

    def value(self, prices):
        return self.cash + sum(prices[t] * self.holdings.get(t, 0) for t in self.holdings)
    

# -------------------------- #
# 2. Define Utility Function # 
# -------------------------- #

def get_factor_models(factor_names):
    """
    Maps factor names to actual factor classes.
    """
    factor_map = {
        'PE': ValueFactor(),
        '12M_Return': MomentumFactor(),
        'MarketCap': SizeFactor(),
        'Volatility': LowVolatilityFactor()
    }
    return [factor_map[name] for name in factor_names if name in factor_map]


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
    import pandas_datareader.data as web
    try:
        ff = web.DataReader('F-F_Research_Data_Factors_daily', 'famafrench')[0]
        ff.index = pd.to_datetime(ff.index, format="%Y%m%d")
        ff = ff.rename(columns=lambda x: x.strip())  # remove trailing spaces
        print("\n✅ Fama-French Data Sample:\n", ff.head())  # ✅ Add this line
        return ff / 100  # convert % to decimal
    except Exception as e:
        print("❌ Failed to load Fama-French data:", e)
        return pd.DataFrame()

# ---------------------------- #
# 3. Define Simulator Function # 
# ---------------------------- #

def run_simulation(tickers, start_date, end_date, initial_cash=100000, selected_factors=None, use_fama_french=False):
    price_data = download_price_data(tickers, start_date, end_date)
    factor_df = calculate_factor_data(price_data, selected_factors or [])

    # Create Security objects
    securities = []
    for ticker in tickers:
        # Create a Security object per stock, bundling its prices and factors.
        prices = price_data[ticker]
        exposures = factor_df.loc[ticker].to_dict()
        securities.append(Security(ticker, prices, exposures))

    dates = price_data.index
    portfolio = Portfolio(initial_cash)

    # Use only user-selected factors
    factors = get_factor_models(selected_factors or [])
    optimizer = RankBasedOptimizer(top_n=3)
    navs = []

    for i, date in enumerate(dates):
        # Monthly rebalance: rank, optimize, rebalance.
        # Track NAV daily for performance.
        if i % 21 == 0:  
            scores = {s.ticker: sum(f.score(s) for f in factors) for s in securities}
            prices = {s.ticker: s.prices[date] for s in securities}
            weights = optimizer.optimize(scores)
            portfolio.rebalance(weights, prices)
        prices = {s.ticker: s.prices[date] for s in securities}
        nav = portfolio.value(prices)
        navs.append((date, nav))

    # Create a NAV dataframe and calculate daily returns.
    nav_df = pd.DataFrame(navs, columns=['Date', 'NAV']).set_index('Date')
    nav_df['Returns'] = nav_df['NAV'].pct_change()

    # Plot NAV to visualize portfolio performance.
    plt.figure(figsize=(10, 5))
    plt.plot(nav_df['NAV'], marker='o')
    plt.title('Factor-Based Portfolio NAV')
    plt.xlabel('Date')
    plt.ylabel('NAV')
    plt.grid(True)
    plt.tight_layout()
    plt.show()

    if use_fama_french:
        # Run a regression to see how well Fama-French factors explain the portfolio’s daily returns.
        try:
            ff = load_fama_french_factors() # Downloads daily Fama-French data 
            if ff.empty:
                raise ValueError("Fama-French data is empty.")

            nav_df = nav_df.copy()
            nav_df.index = pd.to_datetime(nav_df.index).normalize() # Removes the time component from timestamps (ensures exact date match) 
            ff = ff.copy()
            ff.index = pd.to_datetime(ff.index).normalize() # Removes the time component from timestamps (ensures exact date match) 

            merged = nav_df.join(ff, how='inner') # only includes dates that exist in both datasets
            if merged.empty:
                raise ValueError("No overlapping dates between NAV and Fama-French data.")

            merged['Excess_Return'] = merged['Returns'] - merged['RF']
            merged = merged.dropna(subset=['Excess_Return', 'Mkt-RF', 'SMB', 'HML'])

            if merged.empty:
                raise ValueError("All rows dropped due to NaNs in regression variables.")

            print("\n📊 Merged Data Sample:\n", merged[['Returns', 'RF', 'Mkt-RF', 'SMB', 'HML']].head())

            X = sm.add_constant(merged[['Mkt-RF', 'SMB', 'HML']]) # Independent variables 
            y = merged['Excess_Return'] # Dependent variable 
                # Excess_Return = α + β1*Mkt-RF + β2*SMB + β3*HML + ε
                # The result tells how sensitive the portfolio is to each factor 
                # and how much of your performance can be explained by standard market risks.
            model = sm.OLS(y, X).fit()

            print("\n📈 Fama-French 3-Factor Regression Results:")
            print(model.summary())

        except Exception as e:
            print("⚠️ Fama-French attribution failed:", e)

        
    # print("\nNAV Dates Range:", nav_df.index.min(), "to", nav_df.index.max())
    # print("FF Dates Range:", ff.index.min(), "to", ff.index.max())

    return nav_df.tail()
