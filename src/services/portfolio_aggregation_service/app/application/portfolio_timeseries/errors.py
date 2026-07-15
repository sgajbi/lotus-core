"""Application errors raised while materializing portfolio timeseries."""


class PortfolioAggregationSourceMissing(RuntimeError):
    """Reject aggregation when its authoritative portfolio scope is absent."""


class CurrencyReferenceNotFoundError(PortfolioAggregationSourceMissing):
    """Reject aggregation when portfolio or instrument currency is absent."""


class FxRateNotFoundError(PortfolioAggregationSourceMissing):
    """Reject aggregation when a required positive FX rate is unavailable."""


class InstrumentReferenceNotFoundError(PortfolioAggregationSourceMissing):
    """Reject aggregation when a position lacks authoritative instrument data."""
