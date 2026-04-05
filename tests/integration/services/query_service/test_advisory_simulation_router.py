from fastapi.testclient import TestClient

from src.services.query_control_plane_service.app.main import app


def _payload() -> dict:
    return {
        "portfolio_snapshot": {
            "portfolio_id": "pf_core_adv_router",
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
        "proposed_cash_flows": [],
        "proposed_trades": [{"side": "BUY", "instrument_id": "EQ_1", "quantity": "2"}],
    }


def test_advisory_simulation_execution_router_returns_canonical_result():
    with TestClient(app) as client:
        response = client.post(
            "/integration/advisory/proposals/simulate-execution",
            json=_payload(),
            headers={
                "X-Request-Hash": "sha256:router-hash",
                "Idempotency-Key": "idem-router-001",
                "X-Correlation-Id": "corr-router-001",
            },
        )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "READY"
    assert body["correlation_id"] == "corr-router-001"
    assert body["lineage"]["request_hash"] == "sha256:router-hash"
    assert body["lineage"]["idempotency_key"] == "idem-router-001"
