from stock import Stock
from data_loader import load_price_data, load_earnings
from drift_analyzer import DriftAnalyzer
from report import show_drift_summary, plot_drift

def main():
    ticker = "AAPL"
    start = "2021-01-01"
    end = "2023-12-31"

    # Create stock object
    stock = Stock(ticker)

    # Load historical prices
    print(f"Loading price data for {ticker}...")
    stock.set_price_data(load_price_data(ticker, start, end))

    # Load earnings data from FMP
    print(f"Loading earnings reports for {ticker}...")
    earnings_reports = load_earnings(ticker)
    for report in earnings_reports:
        stock.add_earnings(report)

    # Analyze post-earnings drift
    analyzer = DriftAnalyzer(stock)
    analyzer.analyze()
    drift_df = analyzer.get_drift_df()

    # Display results
    show_drift_summary(drift_df)
    plot_drift(drift_df)

if __name__ == "__main__":
    main()