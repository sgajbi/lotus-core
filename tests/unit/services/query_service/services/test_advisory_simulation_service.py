from src.services.query_service.app.advisory_simulation.models import ProposalSimulateRequest
from src.services.query_service.app.services.advisory_simulation_service import (
    execute_advisory_simulation,
)


def _request() -> ProposalSimulateRequest:
    return ProposalSimulateRequest.model_validate(
        {
            "portfolio_snapshot": {
                "portfolio_id": "pf_core_adv_1",
                "base_currency": "USD",
                "positions": [],
                "cash_balances": [{"currency": "USD", "amount": "1000"}],
            },
            "market_data_snapshot": {
                "prices": [{"instrument_id": "EQ_1", "price": "100", "currency": "USD"}],
                "fx_rates": [],
            },
            "shelf_entries": [{"instrument_id": "EQ_1", "status": "APPROVED"}],
            "options": {"enable_proposal_simulation": True},
            "proposed_cash_flows": [{"currency": "USD", "amount": "200"}],
            "proposed_trades": [{"side": "BUY", "instrument_id": "EQ_1", "quantity": "2"}],
        }
    )


def test_execute_advisory_simulation_preserves_supplied_lineage_inputs():
    result = execute_advisory_simulation(
        request=_request(),
        request_hash="sha256:test-hash",
        idempotency_key="idem-core-001",
        correlation_id="corr-core-001",
    )

    assert result.status == "READY"
    assert result.correlation_id == "corr-core-001"
    assert result.lineage.request_hash == "sha256:test-hash"
    assert result.lineage.idempotency_key == "idem-core-001"
    assert [intent.intent_type for intent in result.intents] == [
        "CASH_FLOW",
        "SECURITY_TRADE",
    ]


def test_execute_advisory_simulation_computes_request_hash_when_missing():
    result = execute_advisory_simulation(
        request=_request(),
        request_hash=None,
        idempotency_key=None,
        correlation_id="corr-core-002",
    )

    assert result.lineage.request_hash.startswith("sha256:")
    assert result.correlation_id == "corr-core-002"
