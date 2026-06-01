from datetime import date
from typing import Any

from .position_holdings import (
    HeldSinceRequest,
    apply_held_since_dates,
    effective_holdings_as_of_date,
    fallback_valuation_security_ids,
    held_since_security_epoch_pairs,
    market_price_freshness_security_ids,
    should_fetch_fallback_valuation_map,
    should_use_default_holdings_as_of_date,
)


async def effective_holdings_read_as_of_date(
    *,
    repository: Any,
    requested_as_of_date: date | None,
    include_projected: bool,
) -> date | None:
    latest_business_date = (
        await repository.get_latest_business_date()
        if should_use_default_holdings_as_of_date(
            requested_as_of_date=requested_as_of_date,
            include_projected=include_projected,
        )
        else requested_as_of_date
    )
    return effective_holdings_as_of_date(
        requested_as_of_date=requested_as_of_date,
        latest_business_date=latest_business_date,
        include_projected=include_projected,
    )


async def holdings_position_source_rows(
    *,
    repository: Any,
    portfolio_id: str,
    effective_as_of_date: date | None,
) -> tuple[list[tuple[Any, Any, Any]], list[tuple[Any, Any, Any]]]:
    if effective_as_of_date is not None:
        return (
            await repository.get_latest_positions_by_portfolio_as_of_date(
                portfolio_id, effective_as_of_date
            ),
            await repository.get_latest_position_history_by_portfolio_as_of_date(
                portfolio_id,
                effective_as_of_date,
            ),
        )

    return (
        await repository.get_latest_positions_by_portfolio(portfolio_id),
        await repository.get_latest_position_history_by_portfolio(portfolio_id),
    )


async def fallback_holdings_valuation_map(
    *,
    repository: Any,
    portfolio_id: str,
    effective_as_of_date: date | None,
    db_results: list[tuple[Any, Any, Any]],
    history_supplements: list[tuple[Any, Any, Any]],
    snapshot_security_ids: set[str],
) -> dict[str, dict[str, Any] | None]:
    if not should_fetch_fallback_valuation_map(
        db_results=db_results,
        history_supplements=history_supplements,
        snapshot_security_ids=snapshot_security_ids,
    ):
        return {}

    fallback_security_ids = fallback_valuation_security_ids(history_supplements)
    if effective_as_of_date is not None:
        return await repository.get_latest_snapshot_valuation_map_as_of_date(
            portfolio_id,
            effective_as_of_date,
            security_ids=fallback_security_ids or None,
        )

    return await repository.get_latest_snapshot_valuation_map(
        portfolio_id,
        security_ids=fallback_security_ids or None,
    )


async def holdings_support_evidence(
    *,
    repository: Any,
    portfolio_id: str,
    positions: list[Any],
    held_since_requests: list[HeldSinceRequest],
    response_as_of_date: date,
) -> dict[str, date]:
    if held_since_requests:
        held_since_map = await repository.get_held_since_dates(
            portfolio_id=portfolio_id,
            security_epoch_pairs=held_since_security_epoch_pairs(held_since_requests),
        )
        apply_held_since_dates(
            positions=positions,
            held_since_requests=held_since_requests,
            held_since_map=held_since_map,
        )

    return await repository.get_latest_market_price_dates(
        security_ids=market_price_freshness_security_ids(positions),
        as_of_date=response_as_of_date,
    )
