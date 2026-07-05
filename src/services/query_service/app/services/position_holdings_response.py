from datetime import date
from typing import Any

from ..dtos.position_dto import PortfolioPositionsResponse
from .position_holdings import (
    assign_position_weights,
    holdings_data_quality_status,
    holdings_response_as_of_date,
    latest_holdings_evidence_timestamp,
    merge_snapshot_and_history_position_rows,
    portfolio_position_rows_data,
    portfolio_positions_response_data,
    position_held_since_requests,
)
from .position_holdings_degradation import holdings_degradation_summary
from .position_holdings_reads import (
    fallback_holdings_valuation_map,
    holdings_position_source_rows,
    holdings_support_evidence,
)


async def portfolio_holdings_response(
    *,
    repository: Any,
    portfolio_id: str,
    effective_as_of_date: date | None,
) -> PortfolioPositionsResponse:
    snapshot_results, history_results = await holdings_position_source_rows(
        repository=repository,
        portfolio_id=portfolio_id,
        effective_as_of_date=effective_as_of_date,
    )

    db_results, history_supplements, snapshot_security_ids = (
        merge_snapshot_and_history_position_rows(
            snapshot_results=snapshot_results,
            history_results=history_results,
        )
    )
    fallback_valuation_map = await fallback_holdings_valuation_map(
        repository=repository,
        portfolio_id=portfolio_id,
        effective_as_of_date=effective_as_of_date,
        db_results=db_results,
        history_supplements=history_supplements,
        snapshot_security_ids=snapshot_security_ids,
    )

    positions = portfolio_position_rows_data(
        db_results=db_results,
        snapshot_security_ids=snapshot_security_ids,
        fallback_valuation_map=fallback_valuation_map,
    )
    assign_position_weights(positions)

    held_since_requests = position_held_since_requests(
        db_results=db_results,
        positions=positions,
    )

    response_as_of_date = holdings_response_as_of_date(
        effective_as_of_date=effective_as_of_date,
        positions=positions,
    )
    latest_market_price_dates = await holdings_support_evidence(
        repository=repository,
        portfolio_id=portfolio_id,
        positions=positions,
        held_since_requests=held_since_requests,
        response_as_of_date=response_as_of_date,
    )
    data_quality_status = holdings_data_quality_status(
        positions=positions,
        history_supplements=history_supplements,
        response_as_of_date=response_as_of_date,
        latest_market_price_dates=latest_market_price_dates,
    )
    latest_evidence_timestamp = latest_holdings_evidence_timestamp(db_results)
    return portfolio_positions_response_data(
        portfolio_id=portfolio_id,
        positions=positions,
        response_as_of_date=response_as_of_date,
        data_quality_status=data_quality_status,
        latest_evidence_timestamp=latest_evidence_timestamp,
        degradation=holdings_degradation_summary(
            positions=positions,
            history_supplements=history_supplements,
            fallback_valuation_map=fallback_valuation_map,
            response_as_of_date=response_as_of_date,
            latest_market_price_dates=latest_market_price_dates,
            latest_evidence_timestamp=latest_evidence_timestamp,
        ),
    )
