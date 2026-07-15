"""Map external valuation snapshot events to application commands."""

from portfolio_common.events import DailyPositionSnapshotPersistedEvent

from ...application.position_timeseries import MaterializePositionTimeseriesCommand


def map_position_snapshot_event(
    event: DailyPositionSnapshotPersistedEvent,
    *,
    correlation_id: str | None,
) -> MaterializePositionTimeseriesCommand:
    """Detach the application command from its Pydantic delivery contract."""

    return MaterializePositionTimeseriesCommand(
        snapshot_id=event.id,
        portfolio_id=event.portfolio_id,
        security_id=event.security_id,
        valuation_date=event.date,
        epoch=event.epoch,
        correlation_id=correlation_id or event.correlation_id,
    )
