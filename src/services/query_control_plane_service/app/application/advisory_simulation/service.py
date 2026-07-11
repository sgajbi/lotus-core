"""Application entry point for canonical advisory proposal simulation."""

from __future__ import annotations

from portfolio_common.runtime_providers import IdGenerator

from ...contracts.advisory_simulation_models import (
    ProposalResult,
    ProposalSimulateRequest,
)
from .advisory_engine import (
    run_proposal_simulation,
)
from .common.canonical import (
    hash_canonical_payload,
)


def execute_advisory_simulation(
    *,
    request: ProposalSimulateRequest,
    request_hash: str | None,
    idempotency_key: str | None,
    correlation_id: str | None,
    simulation_contract_version: str,
    id_generator: IdGenerator,
) -> ProposalResult:
    resolved_request_hash = request_hash or hash_canonical_payload(request.model_dump(mode="json"))
    resolved_correlation_id = correlation_id or f"corr_{id_generator.new_hex()[:12]}"
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
