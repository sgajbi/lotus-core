from __future__ import annotations

import uuid

from src.services.query_service.app.advisory_simulation.advisory_engine import (
    run_proposal_simulation,
)
from src.services.query_service.app.advisory_simulation.common.canonical import (
    hash_canonical_payload,
)
from src.services.query_service.app.advisory_simulation.models import (
    ProposalResult,
    ProposalSimulateRequest,
)


def execute_advisory_simulation(
    *,
    request: ProposalSimulateRequest,
    request_hash: str | None,
    idempotency_key: str | None,
    correlation_id: str | None,
    simulation_contract_version: str,
) -> ProposalResult:
    resolved_request_hash = request_hash or hash_canonical_payload(request.model_dump(mode="json"))
    resolved_correlation_id = correlation_id or f"corr_{uuid.uuid4().hex[:12]}"
    return run_proposal_simulation(
        portfolio=request.portfolio_snapshot,
        market_data=request.market_data_snapshot,
        shelf=request.shelf_entries,
        options=request.options,
        proposed_cash_flows=request.proposed_cash_flows,
        proposed_trades=request.proposed_trades,
        reference_model=request.reference_model,
        request_hash=resolved_request_hash,
        idempotency_key=idempotency_key,
        correlation_id=resolved_correlation_id,
        simulation_contract_version=simulation_contract_version,
    )
