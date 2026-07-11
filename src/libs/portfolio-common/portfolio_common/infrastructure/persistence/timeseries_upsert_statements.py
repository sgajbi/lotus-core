"""PostgreSQL upsert statements for position and portfolio timeseries records."""

from typing import Any

from sqlalchemy import func
from sqlalchemy.dialects.postgresql import insert as pg_insert

from portfolio_common.database_models import PortfolioTimeseries, PositionTimeseries

POSITION_TIMESERIES_IDENTITY_COLUMNS = ("portfolio_id", "security_id", "date", "epoch")
PORTFOLIO_TIMESERIES_IDENTITY_COLUMNS = ("portfolio_id", "date", "epoch")
TIMESERIES_AUDIT_COLUMNS = ("created_at", "updated_at")


def build_position_timeseries_upsert_statement(record: Any):
    """Build the idempotent position-timeseries upsert statement."""
    return _timeseries_upsert_statement(
        PositionTimeseries,
        record,
        POSITION_TIMESERIES_IDENTITY_COLUMNS,
    )


def build_portfolio_timeseries_upsert_statement(record: Any):
    """Build the idempotent portfolio-timeseries upsert statement."""
    return _timeseries_upsert_statement(
        PortfolioTimeseries,
        record,
        PORTFOLIO_TIMESERIES_IDENTITY_COLUMNS,
    )


def _timeseries_upsert_statement(
    model: Any,
    record: Any,
    identity_columns: tuple[str, ...],
):
    insert_values = {
        column.name: getattr(record, column.name)
        for column in model.__table__.columns
        if column.name not in TIMESERIES_AUDIT_COLUMNS
    }
    update_values = {
        name: value for name, value in insert_values.items() if name not in identity_columns
    }
    update_values["updated_at"] = func.now()
    return (
        pg_insert(model)
        .values(**insert_values)
        .on_conflict_do_update(index_elements=list(identity_columns), set_=update_values)
    )
