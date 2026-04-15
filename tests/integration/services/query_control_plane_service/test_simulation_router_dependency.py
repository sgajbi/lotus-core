from datetime import datetime, timezone
from unittest.mock import AsyncMock

import httpx
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from src.services.query_control_plane_service.app.main import app
from src.services.query_control_plane_service.app.routers.simulation import (
    SimulationService,
    get_simulation_service,
)

pytestmark = pytest.mark.asyncio


@pytest_asyncio.fixture
async def async_test_client():
    mock_service = AsyncMock()
    app.dependency_overrides[get_simulation_service] = lambda: mock_service
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield client, mock_service
    app.dependency_overrides.pop(get_simulation_service, None)


async def test_create_simulation_session_success(async_test_client):
    client, mock_service = async_test_client
    now = datetime.now(timezone.utc)
    mock_service.create_session.return_value = {
        "session": {
            "session_id": "S1",
            "portfolio_id": "P1",
            "status": "ACTIVE",
            "version": 1,
            "created_by": "tester",
            "created_at": now,
            "expires_at": now,
        }
    }

    response = await client.post(
        "/simulation-sessions", json={"portfolio_id": "P1", "created_by": "tester"}
    )

    assert response.status_code == 201
    assert response.json()["session"]["session_id"] == "S1"


async def test_get_simulation_session_success(async_test_client):
    client, mock_service = async_test_client
    now = datetime.now(timezone.utc)
    mock_service.get_session.return_value = {
        "session": {
            "session_id": "S1",
            "portfolio_id": "P1",
            "status": "ACTIVE",
            "version": 2,
            "created_by": "tester",
            "created_at": now,
            "expires_at": now,
        }
    }

    response = await client.get("/simulation-sessions/S1")

    assert response.status_code == 200
    body = response.json()
    assert body["session"]["session_id"] == "S1"
    assert body["session"]["status"] == "ACTIVE"


async def test_create_simulation_session_unknown_portfolio_maps_to_404(async_test_client):
    client, mock_service = async_test_client
    mock_service.create_session.side_effect = ValueError("Portfolio with id P404 not found")

    response = await client.post(
        "/simulation-sessions", json={"portfolio_id": "P404", "created_by": "tester"}
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Portfolio with id P404 not found"


async def test_get_simulation_session_not_found_maps_to_404(async_test_client):
    client, mock_service = async_test_client
    mock_service.get_session.side_effect = ValueError("not found")

    response = await client.get("/simulation-sessions/S404")

    assert response.status_code == 404


async def test_add_simulation_changes_validation_maps_to_400(async_test_client):
    client, mock_service = async_test_client
    mock_service.add_changes.side_effect = ValueError("session expired")

    response = await client.post(
        "/simulation-sessions/S1/changes",
        json={
            "changes": [{"security_id": "SEC_AAPL_US", "transaction_type": "BUY", "quantity": 10}]
        },
    )

    assert response.status_code == 400


async def test_add_simulation_changes_missing_session_maps_to_404(async_test_client):
    client, mock_service = async_test_client
    mock_service.add_changes.side_effect = ValueError("Simulation session S404 not found")

    response = await client.post(
        "/simulation-sessions/S404/changes",
        json={
            "changes": [{"security_id": "SEC_AAPL_US", "transaction_type": "BUY", "quantity": 10}]
        },
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Simulation session S404 not found"


async def test_add_simulation_changes_success(async_test_client):
    client, mock_service = async_test_client
    now = datetime.now(timezone.utc)
    mock_service.add_changes.return_value = {
        "session_id": "S1",
        "version": 3,
        "changes": [
            {
                "change_id": "SIM-CHG-0001",
                "session_id": "S1",
                "portfolio_id": "P1",
                "security_id": "SEC_AAPL_US",
                "transaction_type": "BUY",
                "quantity": 10.0,
                "price": "210.5000000000",
                "amount": "2105.0000000000",
                "currency": "USD",
                "effective_date": "2026-03-10",
                "metadata": {"source": "gateway"},
                "created_at": now,
            }
        ],
    }

    response = await client.post(
        "/simulation-sessions/S1/changes",
        json={
            "changes": [
                {
                    "security_id": "SEC_AAPL_US",
                    "transaction_type": "BUY",
                    "quantity": 10,
                    "price": "210.5000000000",
                    "currency": "USD",
                    "effective_date": "2026-03-10",
                    "metadata": {"source": "gateway"},
                }
            ]
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["session_id"] == "S1"
    assert body["version"] == 3
    assert body["changes"][0]["change_id"] == "SIM-CHG-0001"
    assert body["changes"][0]["metadata"]["source"] == "gateway"


async def test_get_projected_positions_success(async_test_client):
    client, mock_service = async_test_client
    mock_service.get_projected_positions.return_value = {
        "session_id": "S1",
        "portfolio_id": "P1",
        "baseline_as_of": None,
        "positions": [
            {
                "security_id": "SEC_AAPL_US",
                "instrument_name": "Apple Inc.",
                "asset_class": "Equity",
                "baseline_quantity": 100.0,
                "proposed_quantity": 120.0,
                "delta_quantity": 20.0,
                "cost_basis": 1000.0,
                "cost_basis_local": 1000.0,
            }
        ],
    }

    response = await client.get("/simulation-sessions/S1/projected-positions")

    assert response.status_code == 200
    body = response.json()
    assert body["session_id"] == "S1"
    assert body["positions"][0]["delta_quantity"] == 20.0


async def test_create_simulation_session_unexpected_error_maps_to_500(async_test_client):
    client, mock_service = async_test_client
    mock_service.create_session.side_effect = RuntimeError("db unavailable")

    response = await client.post(
        "/simulation-sessions", json={"portfolio_id": "P1", "created_by": "tester"}
    )

    assert response.status_code == 500
    assert response.json()["detail"] == "Failed to create simulation session."


async def test_close_simulation_session_not_found_maps_to_404(async_test_client):
    client, mock_service = async_test_client
    mock_service.close_session.side_effect = ValueError("not found")

    response = await client.delete("/simulation-sessions/S404")
    assert response.status_code == 404


async def test_close_simulation_session_success(async_test_client):
    client, mock_service = async_test_client
    now = datetime.now(timezone.utc)
    mock_service.close_session.return_value = {
        "session": {
            "session_id": "S1",
            "portfolio_id": "P1",
            "status": "CLOSED",
            "version": 4,
            "created_by": "tester",
            "created_at": now,
            "expires_at": now,
        }
    }

    response = await client.delete("/simulation-sessions/S1")

    assert response.status_code == 200
    body = response.json()
    assert body["session"]["session_id"] == "S1"
    assert body["session"]["status"] == "CLOSED"


async def test_delete_simulation_change_validation_maps_to_400(async_test_client):
    client, mock_service = async_test_client
    mock_service.delete_change.side_effect = ValueError("invalid")

    response = await client.delete("/simulation-sessions/S1/changes/C404")
    assert response.status_code == 400


async def test_delete_simulation_change_not_found_maps_to_404(async_test_client):
    client, mock_service = async_test_client
    mock_service.delete_change.side_effect = ValueError("Simulation change C404 not found")

    response = await client.delete("/simulation-sessions/S1/changes/C404")

    assert response.status_code == 404
    assert response.json()["detail"] == "Simulation change C404 not found"


async def test_delete_simulation_change_success(async_test_client):
    client, mock_service = async_test_client
    now = datetime.now(timezone.utc)
    mock_service.delete_change.return_value = {
        "session_id": "S1",
        "version": 4,
        "changes": [
            {
                "change_id": "SIM-CHG-0002",
                "session_id": "S1",
                "portfolio_id": "P1",
                "security_id": "SEC_MSFT_US",
                "transaction_type": "SELL",
                "quantity": 5.0,
                "price": "395.0000000000",
                "amount": "1975.0000000000",
                "currency": "USD",
                "effective_date": "2026-03-11",
                "metadata": {"source": "gateway"},
                "created_at": now,
            }
        ],
    }

    response = await client.delete("/simulation-sessions/S1/changes/C1")

    assert response.status_code == 200
    body = response.json()
    assert body["session_id"] == "S1"
    assert body["version"] == 4
    assert body["changes"][0]["change_id"] == "SIM-CHG-0002"


async def test_get_projected_positions_not_found_maps_to_404(async_test_client):
    client, mock_service = async_test_client
    mock_service.get_projected_positions.side_effect = ValueError("not found")

    response = await client.get("/simulation-sessions/S404/projected-positions")
    assert response.status_code == 404


async def test_get_projected_summary_not_found_maps_to_404(async_test_client):
    client, mock_service = async_test_client
    mock_service.get_projected_summary.side_effect = ValueError("not found")

    response = await client.get("/simulation-sessions/S404/projected-summary")
    assert response.status_code == 404


async def test_get_projected_summary_success(async_test_client):
    client, mock_service = async_test_client
    mock_service.get_projected_summary.return_value = {
        "session_id": "S1",
        "portfolio_id": "P1",
        "total_baseline_positions": 2,
        "total_proposed_positions": 3,
        "net_delta_quantity": 25.0,
    }

    response = await client.get("/simulation-sessions/S1/projected-summary")
    assert response.status_code == 200
    payload = response.json()
    assert payload["session_id"] == "S1"
    assert payload["net_delta_quantity"] == 25.0


async def test_get_simulation_service_dependency_factory():
    db = AsyncMock(spec=AsyncSession)

    service = get_simulation_service(db)

    assert isinstance(service, SimulationService)
