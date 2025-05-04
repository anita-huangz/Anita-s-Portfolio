class Stock:
    def __init__(self, ticker):
        self.ticker = ticker
        self.earnings = []  # list of EarningsReport
        self.price_data = None  # Pandas DataFrame

    def add_earnings(self, report):
        self.earnings.append(report)

    def set_price_data(self, df):
        self.price_data = df