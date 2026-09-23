"""Position snapshot selection for stable analytics pagination."""

from datetime import date

from ...contracts.analytics_inputs import AnalyticsWindow, PositionAnalyticsTimeseriesRequest
from ...ports.analytics import AnalyticsTimeseriesReader
from .analytics_pagination import PositionTimeseriesCursor


async def position_snapshot_epoch(
    *,
    reader: AnalyticsTimeseriesReader,
    portfolio_id: str,
    request: PositionAnalyticsTimeseriesRequest,
    resolved_window: AnalyticsWindow,
    dimension_filters: dict[str, set[str]],
    cursor: PositionTimeseriesCursor,
    governed_business_dates: list[date],
    business_calendar_present: bool,
) -> int:
    """Reuse a cursor epoch or bind a new one to the captured calendar scope."""

    if cursor.snapshot_epoch is not None:
        return cursor.snapshot_epoch
    return await reader.get_position_snapshot_epoch(
        portfolio_id=portfolio_id,
        start_date=resolved_window.start_date,
        end_date=resolved_window.end_date,
        security_ids=request.filters.security_ids,
        position_ids=request.filters.position_ids,
        dimension_filters=dimension_filters,
        governed_business_dates=governed_business_dates,
        business_calendar_present=business_calendar_present,
    )
