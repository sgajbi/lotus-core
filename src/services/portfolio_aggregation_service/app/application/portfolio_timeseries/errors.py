"""Application errors raised while materializing portfolio timeseries."""


class PortfolioAggregationSourceMissing(RuntimeError):
    """Reject aggregation when its authoritative portfolio scope is absent."""
