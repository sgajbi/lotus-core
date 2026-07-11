from portfolio_common.infrastructure.persistence.timeseries_repository import (
    SharedTimeseriesRepository,
)


class TimeseriesRepository(SharedTimeseriesRepository):
    """Portfolio aggregation service wrapper for shared timeseries repository logic."""
