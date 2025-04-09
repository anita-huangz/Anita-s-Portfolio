from models import ValueFactor, MomentumFactor, SizeFactor, LowVolatilityFactor

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
