from __future__ import annotations

from datetime import date
from typing import Any

from portfolio_common.database_models import (
    InstrumentEligibilityProfile,
    ModelPortfolioTarget,
    PortfolioMandateBinding,
)
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


def ranked_portfolio_mandate_binding_ids(*predicates: Any):
    return (
        select(
            PortfolioMandateBinding.id.label("id"),
            func.row_number()
            .over(
                partition_by=(
                    PortfolioMandateBinding.portfolio_id,
                    PortfolioMandateBinding.mandate_id,
                ),
                order_by=(
                    PortfolioMandateBinding.effective_from.desc(),
                    PortfolioMandateBinding.observed_at.desc().nullslast(),
                    PortfolioMandateBinding.binding_version.desc(),
                    PortfolioMandateBinding.updated_at.desc(),
                    PortfolioMandateBinding.created_at.desc(),
                    PortfolioMandateBinding.id.desc(),
                ),
            )
            .label("rn"),
        )
        .where(*predicates)
        .subquery()
    )


def ranked_model_portfolio_target_ids(*predicates: Any):
    return (
        select(
            ModelPortfolioTarget.id.label("id"),
            func.row_number()
            .over(
                partition_by=(
                    ModelPortfolioTarget.model_portfolio_id,
                    ModelPortfolioTarget.model_portfolio_version,
                    ModelPortfolioTarget.instrument_id,
                ),
                order_by=(
                    ModelPortfolioTarget.effective_from.desc(),
                    ModelPortfolioTarget.updated_at.desc(),
                    ModelPortfolioTarget.created_at.desc(),
                    ModelPortfolioTarget.id.desc(),
                ),
            )
            .label("rn"),
        )
        .where(*predicates)
        .subquery()
    )


def ranked_instrument_eligibility_ids(security_id_expr: Any, *predicates: Any):
    return (
        select(
            InstrumentEligibilityProfile.id.label("id"),
            func.row_number()
            .over(
                partition_by=security_id_expr,
                order_by=(
                    InstrumentEligibilityProfile.effective_from.desc(),
                    InstrumentEligibilityProfile.observed_at.desc().nullslast(),
                    InstrumentEligibilityProfile.eligibility_version.desc(),
                    InstrumentEligibilityProfile.updated_at.desc(),
                    InstrumentEligibilityProfile.created_at.desc(),
                    InstrumentEligibilityProfile.id.desc(),
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
