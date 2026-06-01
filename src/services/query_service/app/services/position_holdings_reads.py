from datetime import date
from typing import Any

from .position_holdings import (
    fallback_valuation_security_ids,
    should_fetch_fallback_valuation_map,
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
