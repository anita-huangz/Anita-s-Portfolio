# Factor-Based Portfolio Optimization

## Overview
This project implements a factor-based portfolio optimization model that utilizes historical asset returns, market factors, and statistical modeling techniques to allocate portfolio weights dynamically based on factor exposures. The project incorporates Fama-French factors, interest rates, volatility measures, and bond spreads to estimate expected asset returns and optimize portfolio allocation.

## Features
1. **Historical Data Collection**: Retrieves daily adjusted closing prices for selected assets from Yahoo Finance and Fama-French factor data from Kenneth French's Data Library.
2. **Factor Model Construction**: Uses Ordinary Least Squares (OLS) regression to estimate factor loadings for each asset.
3. **Expected Returns Calculation**: Computes expected returns using trained factor models.
4. **Portfolio Optimization**: Utilizes constrained optimization techniques to allocate weights to assets based on factor risk exposure and Sharpe ratio adjustments.
5. **Portfolio Performance Analysis**: Evaluates expected returns, volatility, and Sharpe ratios against a benchmark portfolio (60% Russell 3000, 40% Bloomberg Aggregate Bond Index).
6. **Visualization**: Plots cumulative portfolio returns over time for comparison.

## Data Sources
1. **Yahoo Finance**: Used to collect price and volatility data.
2. **Fama-French Data Library**: Provides factor data for asset pricing models.
3. **Federal Reserve Economic Data (FRED)**: Sources interest rate and liquidity-related indicators.

## Installation
To run the project, install the required dependencies using:
pip install yfinance pandas numpy statsmodels pandas-datareader scipy fredapi matplotlib

## Usage
1. **Collect Historical Data**: Retrieves asset prices, factor data, interest rates, and volatility measures.
2. **Align Data and Split Dataset**: Joins asset returns with factor data and splits the dataset into training, validation, and test sets.
3. **Train Factor Models**: Fits a multiple regression model for each asset to estimate factor loadings.
4. **Validate Model Predictions**: Computes predicted returns and evaluates model performance using Mean Squared Error (MSE).
5. **Calculate Expected Returns**: Uses factor model outputs to compute expected annualized asset returns.
6. **Optimize Portfolio Weights**: Solves a constrained optimization problem to determine optimal asset allocations based on factor exposures and risk preferences.
7. **Evaluate Portfolio Performance**: Computes annualized returns, volatility, and Sharpe ratios for the optimized portfolio.
8. **Plot Cumulative Returns**: Visualizes portfolio performance over time.

## Key Libraries Used
1. **yfinance**: Fetches asset price data.
2. **pandas & numpy**: Data handling and numerical computations.
3. **statsmodels**: Performs regression analysis.
4. **pandas-datareader**: Retrieves macroeconomic and financial data.
5. **scipy.optimize**: Solves portfolio optimization problems.
6. **matplotlib**: Generates performance plots.