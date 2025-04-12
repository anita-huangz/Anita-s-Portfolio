import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import statsmodels.api as sm
from models import Security, Portfolio, RankBasedOptimizer
from utils import get_factor_models
from data import download_price_data, calculate_factor_data, load_fama_french_factors

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

def performance_metrics(nav_df):
    returns = nav_df['Returns'].dropna()
    total_return = nav_df['NAV'].iloc[-1] / nav_df['NAV'].iloc[0] - 1
    annualized_return = (1 + total_return) ** (252 / len(nav_df)) - 1
    volatility = returns.std() * np.sqrt(252)
    sharpe = (returns.mean() * 252) / (returns.std() * np.sqrt(252))
    max_drawdown = ((nav_df['NAV'].cummax() - nav_df['NAV']) / nav_df['NAV'].cummax()).max()

    return {
        "Annualized Return": annualized_return,
        "Volatility": volatility,
        "Sharpe Ratio": sharpe,
        "Max Drawdown": max_drawdown
    }