from datetime import date
from typing import Any

from ..application.holdings_reconciliation import (
    holdings_reconciliation_evidence_hash,
    holdings_reconciliation_evidence_scopes,
    holdings_reconciliation_status,
    is_qualified_closed_cohort,
    latest_reconciliation_evidence_timestamp,
)
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
    valuation_fx_evidence_by_security,
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
    valuation_fx_rate_dates, missing_currency_lineage_security_ids = (
        valuation_fx_evidence_by_security(
            db_results=db_results,
            snapshot_security_ids=snapshot_security_ids,
            fallback_valuation_map=fallback_valuation_map,
        )
    )
    assign_position_weights(positions)

    held_since_requests = position_held_since_requests(
        db_results=db_results,
        positions=positions,
    )

    reconciliation_evidence = await repository.get_holdings_reconciliation_evidence(
        portfolio_id=portfolio_id,
        as_of_date=effective_as_of_date,
    )
    reconciliation_scopes = holdings_reconciliation_evidence_scopes(reconciliation_evidence)
    closed_cohort = is_qualified_closed_cohort(reconciliation_evidence, reconciliation_scopes)
    response_as_of_date = holdings_response_as_of_date(
        effective_as_of_date=effective_as_of_date,
        positions=positions,
    )
    if effective_as_of_date is None and not positions and closed_cohort:
        response_as_of_date = max(
            (scope.business_date for scope in reconciliation_scopes.items),
            default=response_as_of_date,
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
        valuation_fx_rate_dates=valuation_fx_rate_dates,
        missing_currency_lineage_security_ids=missing_currency_lineage_security_ids,
    )
    latest_evidence_timestamp = latest_holdings_evidence_timestamp(db_results)
    if not positions and closed_cohort:
        data_quality_status = "COMPLETE"
    reconciliation_scope_hash = holdings_reconciliation_evidence_hash(
        reconciliation_evidence, reconciliation_scopes
    )
    latest_evidence_timestamp = max(
        (
            timestamp
            for timestamp in (
                latest_evidence_timestamp,
                latest_reconciliation_evidence_timestamp(reconciliation_evidence),
            )
            if timestamp is not None
        ),
        default=None,
    )
    reconciliation_controls = await repository.get_holdings_reconciliation_controls(
        portfolio_id=portfolio_id,
        scopes=reconciliation_scopes.items,
    )
    return portfolio_positions_response_data(
        portfolio_id=portfolio_id,
        positions=positions,
        response_as_of_date=response_as_of_date,
        data_quality_status=data_quality_status,
        latest_evidence_timestamp=latest_evidence_timestamp,
        reconciliation_status=holdings_reconciliation_status(
            scopes=reconciliation_scopes,
            controls=reconciliation_controls,
        ),
        reconciliation_scope_hash=reconciliation_scope_hash,
        degradation=holdings_degradation_summary(
            positions=positions,
            history_supplements=history_supplements,
            fallback_valuation_map=fallback_valuation_map,
            response_as_of_date=response_as_of_date,
            latest_market_price_dates=latest_market_price_dates,
            valuation_fx_rate_dates=valuation_fx_rate_dates,
            missing_currency_lineage_security_ids=missing_currency_lineage_security_ids,
            latest_evidence_timestamp=latest_evidence_timestamp,
            reconciliation_scopes=reconciliation_scopes,
            reconciliation_controls=reconciliation_controls,
            known_closed_cohort=closed_cohort,
        ),
    )
