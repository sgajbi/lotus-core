from __future__ import annotations

from datetime import date
from typing import Any

from portfolio_common.database_models import PortfolioMandateBinding
from sqlalchemy import and_, func, or_, select, tuple_


def dpm_portfolio_universe_stmt(
    *,
    as_of_date: date,
    booking_center_code: str | None = None,
    model_portfolio_ids: list[str] | None = None,
    include_inactive_mandates: bool = False,
    after_sort_key: tuple[str, str] | None = None,
    limit: int | None = None,
):
    ranked = _ranked_dpm_portfolio_universe_binding_ids(
        *_dpm_portfolio_universe_predicates(
            as_of_date=as_of_date,
            booking_center_code=booking_center_code,
            model_portfolio_ids=model_portfolio_ids,
            include_inactive_mandates=include_inactive_mandates,
        )
    )
    stmt = (
        select(PortfolioMandateBinding)
        .join(ranked, PortfolioMandateBinding.id == ranked.c.id)
        .where(ranked.c.rn == 1)
        .order_by(
            PortfolioMandateBinding.portfolio_id.asc(),
            PortfolioMandateBinding.mandate_id.asc(),
        )
    )
    if after_sort_key is not None:
        stmt = stmt.where(
            tuple_(
                PortfolioMandateBinding.portfolio_id,
                PortfolioMandateBinding.mandate_id,
            )
            > after_sort_key
        )
    if limit is not None:
        stmt = stmt.limit(limit)
    return stmt


def _dpm_portfolio_universe_predicates(
    *,
    as_of_date: date,
    booking_center_code: str | None,
    model_portfolio_ids: list[str] | None,
    include_inactive_mandates: bool,
) -> list[Any]:
    predicates = [
        PortfolioMandateBinding.mandate_type == "discretionary",
        _effective_reference_filter(
            PortfolioMandateBinding.effective_from,
            PortfolioMandateBinding.effective_to,
            as_of_date,
        ),
    ]
    if booking_center_code:
        predicates.append(PortfolioMandateBinding.booking_center_code == booking_center_code)
    if model_portfolio_ids:
        predicates.append(PortfolioMandateBinding.model_portfolio_id.in_(model_portfolio_ids))
    if not include_inactive_mandates:
        predicates.append(PortfolioMandateBinding.discretionary_authority_status == "active")
    return predicates


def _effective_reference_filter(
    effective_from_column: Any,
    effective_to_column: Any,
    as_of_date: date,
):
    return and_(
        effective_from_column <= as_of_date,
        or_(effective_to_column.is_(None), effective_to_column >= as_of_date),
    )


def _ranked_dpm_portfolio_universe_binding_ids(*predicates: Any):
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
