"""SQL helpers for deterministic effective-dated client-profile selection."""

from datetime import date
from typing import Any

from sqlalchemy import and_, func, or_, select


def effective_on(effective_from: Any, effective_to: Any, as_of_date: date) -> Any:
    """Match a closed-open nullable effective window on a business date."""

    return and_(
        effective_from <= as_of_date,
        or_(effective_to.is_(None), effective_to >= as_of_date),
    )


def ranked_latest_ids(
    model: Any,
    *partition_columns: Any,
    predicates: list[Any],
    order_by: tuple[Any, ...],
) -> Any:
    """Rank effective rows so adapters can select one deterministic record per domain key."""

    return (
        select(
            model.id.label("id"),
            func.row_number().over(partition_by=partition_columns, order_by=order_by).label("rn"),
        )
        .where(*predicates)
        .subquery()
    )
