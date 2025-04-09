from abc import ABC, abstractmethod

# -------------------------------------- #
# Security class: Encapsulates one stock
# -------------------------------------- #
class Security:
    """
    Represents a single stock/security.

    Attributes:
        ticker (str): Ticker symbol of the security.
        prices (pd.Series): Historical price data.
        factor_exposures (dict): Factor values like PE, volatility, etc.
    """
    def __init__(self, ticker, prices, factor_exposures):
        self.ticker = ticker
        self.prices = prices
        self.factor_exposures = factor_exposures

# -------------------------------------- #
# Abstract base for Factor Models
# -------------------------------------- #
class FactorModel(ABC):
    """
    Abstract base class for all factor models.

    Requires implementing a `score` method that takes a Security object and returns a numeric score.
    """
    @abstractmethod
    def score(self, security):
        pass

# -------------------------------------- #
# Concrete Factor Implementations
# -------------------------------------- #
class ValueFactor(FactorModel):
    """
    Value factor using inverse of PE ratio. Lower PE = better value.
    """
    def score(self, security):
        return 1 / security.factor_exposures['PE']

class MomentumFactor(FactorModel):
    """
    Momentum factor using 12-month return.
    """
    def score(self, security):
        return security.factor_exposures['12M_Return']

class SizeFactor(FactorModel):
    """
    Size factor using negative market cap. Smaller cap preferred.
    """
    def score(self, security):
        return -security.factor_exposures['MarketCap']

class LowVolatilityFactor(FactorModel):
    """
    Low volatility factor using negative standard deviation. Lower vol preferred.
    """
    def score(self, security):
        return -security.factor_exposures['Volatility']

# -------------------------------------- #
# Optimizer for Portfolio Weights
# -------------------------------------- #
class RankBasedOptimizer:
    """
    Simple optimizer that ranks stocks by score and selects the top N equally weighted.

    Attributes:
        top_n (int): Number of top-scoring stocks to include in portfolio.
    """
    def __init__(self, top_n=3):
        self.top_n = top_n

    def optimize(self, scores):
        # top = sorted(scores, key=scores.get, reverse=True)[:self.top_n]
        # return {ticker: 1 / self.top_n for ticker in top}
        """
        Give more weight to higher-scoring stocks instead of equal weight
        """
        top = sorted(scores.items(), key=lambda x: x[1], reverse=True)[:self.top_n]
        total = sum(score for _, score in top)
        return {ticker: score / total for ticker, score in top}

# -------------------------------------- #
# Portfolio class: tracks holdings & cash
# -------------------------------------- #
class Portfolio:
    """
    Simulates a trading portfolio.date_parser

    Attributes:
        cash (float): Uninvested capital.
        holdings (dict): Mapping of tickers to shares held.
        history (list): Historical NAV records.
    """
    def __init__(self, initial_cash):
        self.cash = initial_cash
        self.holdings = {}
        self.history = []

    def rebalance(self, weights, prices):
        """
        Allocates capital based on target weights and current prices.

        Args:
            weights (dict): Ticker to portfolio weight.
            prices (dict): Ticker to price.
        """
        total_value = self.cash + sum(prices[t] * self.holdings.get(t, 0) for t in weights)
        self.holdings = {t: (weights[t] * total_value) / prices[t] for t in weights}
        self.cash = 0

    def value(self, prices):
        """
        Computes total portfolio value using latest prices.

        Args:
            prices (dict): Ticker to price.
        Returns:
            float: Total portfolio value.
        """
        return self.cash + sum(prices[t] * self.holdings.get(t, 0) for t in self.holdings)
