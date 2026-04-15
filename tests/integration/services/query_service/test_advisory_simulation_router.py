from fastapi.testclient import TestClient

from src.services.query_control_plane_service.app.contracts import (
    ADVISORY_SIMULATION_CONTRACT_VERSION,
    ADVISORY_SIMULATION_CONTRACT_VERSION_HEADER,
)
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
                ADVISORY_SIMULATION_CONTRACT_VERSION_HEADER: ADVISORY_SIMULATION_CONTRACT_VERSION,
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
    assert body["lineage"]["simulation_contract_version"] == ADVISORY_SIMULATION_CONTRACT_VERSION
    assert (
        response.headers[ADVISORY_SIMULATION_CONTRACT_VERSION_HEADER]
        == ADVISORY_SIMULATION_CONTRACT_VERSION
    )


def test_advisory_simulation_execution_router_rejects_contract_version_mismatch():
    with TestClient(app) as client:
        response = client.post(
            "/integration/advisory/proposals/simulate-execution",
            json=_payload(),
            headers={ADVISORY_SIMULATION_CONTRACT_VERSION_HEADER: "advisory-simulation.v0"},
        )

    assert response.status_code == 412
    assert response.headers["content-type"].startswith("application/problem+json")
    assert (
        response.headers[ADVISORY_SIMULATION_CONTRACT_VERSION_HEADER]
        == ADVISORY_SIMULATION_CONTRACT_VERSION
    )
    body = response.json()
    assert body["error_code"] == "CANONICAL_SIMULATION_CONTRACT_VERSION_MISMATCH"
    assert body["contract_version"] == ADVISORY_SIMULATION_CONTRACT_VERSION


def test_advisory_simulation_execution_router_returns_problem_details_on_validation_error():
    with TestClient(app) as client:
        response = client.post(
            "/integration/advisory/proposals/simulate-execution",
            json={"portfolio_snapshot": {"portfolio_id": "pf_incomplete"}},
            headers={
                ADVISORY_SIMULATION_CONTRACT_VERSION_HEADER: ADVISORY_SIMULATION_CONTRACT_VERSION
            },
        )

    assert response.status_code == 422
    assert response.headers["content-type"].startswith("application/problem+json")
    assert (
        response.headers[ADVISORY_SIMULATION_CONTRACT_VERSION_HEADER]
        == ADVISORY_SIMULATION_CONTRACT_VERSION
    )
    body = response.json()
    assert body["error_code"] == "CANONICAL_SIMULATION_REQUEST_VALIDATION_FAILED"
    assert body["contract_version"] == ADVISORY_SIMULATION_CONTRACT_VERSION


def test_advisory_simulation_execution_router_returns_problem_details_on_execution_failure(
    monkeypatch,
):
    def _raise_runtime_error(**kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(
        "src.services.query_control_plane_service.app.routers.advisory_simulation.execute_advisory_simulation",
        _raise_runtime_error,
    )

    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.post(
            "/integration/advisory/proposals/simulate-execution",
            json=_payload(),
            headers={
                ADVISORY_SIMULATION_CONTRACT_VERSION_HEADER: ADVISORY_SIMULATION_CONTRACT_VERSION
            },
        )

    assert response.status_code == 500
    assert response.headers["content-type"].startswith("application/problem+json")
    assert (
        response.headers[ADVISORY_SIMULATION_CONTRACT_VERSION_HEADER]
        == ADVISORY_SIMULATION_CONTRACT_VERSION
    )
    body = response.json()
    assert body["error_code"] == "CANONICAL_SIMULATION_EXECUTION_FAILED"
    assert body["contract_version"] == ADVISORY_SIMULATION_CONTRACT_VERSION


def test_advisory_simulation_execution_openapi_documents_contract_header_and_errors():
    with TestClient(app) as client:
        openapi = client.get("/openapi.json").json()

    operation = openapi["paths"]["/integration/advisory/proposals/simulate-execution"]["post"]
    parameter_names = {parameter["name"] for parameter in operation["parameters"]}
    problem_details = openapi["components"]["schemas"]["CanonicalSimulationProblemDetails"]

    assert ADVISORY_SIMULATION_CONTRACT_VERSION_HEADER in parameter_names
    assert "412" in operation["responses"]
    assert "422" in operation["responses"]
    assert "500" in operation["responses"]
    assert "deterministic core-state execution projection only" in operation["description"]
    assert problem_details["properties"]["detail"]["examples"] == [
        "Unsupported canonical simulation contract version: "
        "advisory-simulation.v0. Expected advisory-simulation.v1."
    ]
    assert problem_details["properties"]["contract_version"]["examples"] == [
        ADVISORY_SIMULATION_CONTRACT_VERSION
    ]
