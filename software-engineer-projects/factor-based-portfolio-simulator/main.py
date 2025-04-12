from datetime import datetime
from simulation import run_simulation
from simulation import performance_metrics

# -----------------------------
# main.py: Entry point
# -----------------------------

"""
You're simulating a portfolio that:
- Starts with $100,000 in cash
- Invests in 5 top tech stocks
- Uses historical data from Jan 1, 2022 to Dec 31, 2024 

run_simulation():
- Downloads price data via yfinance
- Mocks factor data (PE ratio, Market Cap, 12M return, volatility)
- Constructs Security objects to encapsulate that data
- Scores stocks monthly using the factors that you have selected 
- Uses a rank-based optimizer to:
    Select the top 3 stocks
    Allocate capital equally among them
- Rebalances every 21 trading days (~1 month)
- Tracks portfolio value (NAV) over time
"""

def main():
    tickers = ['AAPL', 'MSFT', 'GOOGL', 'AMZN', 'META']
    start_date = '2022-01-01'
    end_date = '2025-04-08'
    initial_cash = 100000

    # 👇 Just change this to try new combinations!
    # selected_factors = ['PE', '12M_Return']  # Value + Momentum
    selected_factors = ['MarketCap', 'Volatility']  # Size + Low Vol

    use_fama_french = True

    nav_df = run_simulation(tickers, start_date, end_date, initial_cash, selected_factors, use_fama_french)
    print("\nFinal NAV Results:")
    print(nav_df.tail())

    print(performance_metrics(nav_df))

if __name__ == '__main__':
    main()
