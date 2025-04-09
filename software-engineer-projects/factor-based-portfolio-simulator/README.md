## Goal of the Simulator 

✅ 1. Evaluate Investment Strategy Performance
- Test how well a **Value + Momentum** strategy works over time.
- See if selecting the top 3 stocks based on these factors leads to outperformance.

✅ 2. Simulate Portfolio Mechanics
- Show how your portfolio would rebalance monthly.
- Track NAV (Net Asset Value) to visualize growth.
- Output daily returns so you can compute performance metrics.

✅ 3. Lay the Foundation for Strategy Development
It gives you a framework to:
- Add/remove factors (e.g., Size, Quality)
- Change weighting strategies
- Introduce machine learning-based signals
- Incorporate risk models or transaction costs

## Goal of the Farma-French 3-factor model 

Ran a regression of your daily excess returns (portfolio return minus risk-free rate) against the Fama-French 3 factors:
- Mkt-RF: Market excess return
- SMB: Small Minus Big (size factor)
- HML: High Minus Low (value factor)

### Scenario 1: Backtesting a Factor-Based Strategy on Top Tech Stocks (2022–2024)

**📌 What It Is:**
A historical simulation of a portfolio that:
- Starts with $100,000
- Invests in 5 leading tech stocks: AAPL, MSFT, GOOGL, AMZN, and META
- Runs from January 1, 2022 to December 31, 2024
- Rebalances monthly based on a combined Value (1/PE) and Momentum (12M return) factor model
- Uses **equal weighting(probably need to change this)** for the top 3 ranked stocks at each rebalance

**📈 Key Findings (Based on Final Output):**
- The portfolio grew from $100,000 to ~$156,500, indicating a ~56% total return over 3 years
- Returns varied day-to-day, showing exposure to market volatility (e.g., small dips in late Dec 2024)
- The combined **Value + Momentum** strategy appeared effective during this tech-dominated time frame

**🔢 Key Numbers from the Output:**

| **Coefficient** | **Value** | **Interpretation** |
|------------------|----------:|--------------------|
| `const`          | 0.0004    | Daily alpha (unexplained return) — **not statistically significant** (p = 0.393) |
| `Mkt-RF`         | 1.3606    | Very high exposure to the market. taking **more market risk than average** |
| `SMB`            | -0.2961   | Negative loading on SMB — favor **large-cap stocks** |
| `HML`            | -0.5921   | Negative exposure to value — tilting toward **growth stocks** |
| **R-squared**    | 0.687     | ~69% of the portfolio returns are explained by the Fama-French model |
| **P-values**     | All < 0.001 except `const` | Statistically significant results (**except alpha**) |
