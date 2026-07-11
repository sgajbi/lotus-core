from __future__ import annotations

from datetime import date
from typing import Any

from sqlalchemy import and_, case, func, or_, select


def effective_filter(
    effective_from_column: Any,
    effective_to_column: Any,
    as_of_date: date,
):
    return and_(
        effective_from_column <= as_of_date,
        or_(effective_to_column.is_(None), effective_to_column >= as_of_date),
    )


def normalize_reference_status(status: str) -> str:
    return status.strip().lower()


def canonical_series_ranked_subquery(model: Any, *partition_columns: Any, predicates: Any):
    accepted_quality_rank = case(
        (func.upper(func.trim(model.quality_status)) == "ACCEPTED", 1),
        else_=0,
    )
    return (
        select(
            model.id.label("id"),
            func.row_number()
            .over(
                partition_by=partition_columns,
                order_by=(
                    accepted_quality_rank.desc(),
                    model.source_timestamp.desc().nullslast(),
                    model.series_id.desc(),
                    model.source_vendor.desc().nullslast(),
                    model.source_record_id.desc().nullslast(),
                    model.id.desc(),
                ),
            )
            .label("rn"),
        )
        .where(*predicates)
        .subquery()
    )


def ranked_latest_effective_ids(
    model: Any,
    *partition_columns: Any,
    predicates: list[Any],
    order_by: tuple[Any, ...],
):
    return (
        select(
            model.id.label("id"),
            func.row_number()
            .over(
                partition_by=partition_columns,
                order_by=order_by,
            )
            .label("rn"),
        )
        .where(*predicates)
        .subquery()
    )
