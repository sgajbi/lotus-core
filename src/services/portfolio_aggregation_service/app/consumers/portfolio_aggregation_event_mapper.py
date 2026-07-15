"""Map external portfolio aggregation events to application commands."""

from portfolio_common.events import PortfolioAggregationRequiredEvent

from ..application.portfolio_timeseries import MaterializePortfolioTimeseriesCommand


def map_portfolio_aggregation_event(
    event: PortfolioAggregationRequiredEvent,
    *,
    correlation_id: str | None,
) -> MaterializePortfolioTimeseriesCommand:
    """Detach the application command from its Pydantic delivery contract."""

    return MaterializePortfolioTimeseriesCommand(
        portfolio_id=event.portfolio_id,
        aggregation_date=event.aggregation_date,
        correlation_id=correlation_id or event.correlation_id,
    )
