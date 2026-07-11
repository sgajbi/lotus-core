"""Deterministic SQL ranking shared by QCP time-series source adapters."""

from typing import Any

from sqlalchemy import case, func, select


def canonical_series_ids(model: Any, *partition_columns: Any, predicates: tuple[Any, ...]) -> Any:
    """Rank one preferred source row per series business key."""

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
                    model.source_timestamp.desc().nulls_last(),
                    model.series_id.desc(),
                    model.source_vendor.desc().nulls_last(),
                    model.source_record_id.desc().nulls_last(),
                    model.id.desc(),
                ),
            )
            .label("rn"),
        )
        .where(*predicates)
        .subquery()
    )
