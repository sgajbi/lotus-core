from datetime import UTC, date, datetime
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
import pytest_asyncio

from src.services.query_control_plane_service.app.main import app
from src.services.query_control_plane_service.app.routers.integration import (
    get_core_snapshot_service,
    get_integration_service,
)
from src.services.query_service.app.dtos.integration_dto import (
    EffectiveIntegrationPolicyResponse,
    PolicyProvenanceMetadata,
)
from src.services.query_service.app.dtos.source_data_product_identity import (
    source_data_product_runtime_metadata,
)

pytestmark = pytest.mark.asyncio


@pytest_asyncio.fixture
async def async_test_client():
    mock_core_snapshot_service = MagicMock()
    mock_core_snapshot_service.get_core_snapshot = AsyncMock(
        return_value={
            "portfolio_id": "PORT-INT-001",
            "snapshot_mode": "BASELINE",
            "contract_version": "rfc_081_v1",
            "request_fingerprint": "fp-core-001",
            "freshness": {
                "freshness_status": "CURRENT_SNAPSHOT",
                "baseline_source": "position_state",
                "snapshot_timestamp": "2026-02-27T00:00:00Z",
                "snapshot_epoch": 7,
                "fallback_reason": None,
            },
            "governance": {
                "consumer_system": "lotus-gateway",
                "tenant_id": "default",
                "requested_sections": ["positions_baseline"],
                "applied_sections": ["positions_baseline"],
                "dropped_sections": [],
                "policy_provenance": {
                    "policy_version": "tenant-default-v1",
                    "policy_source": "default",
                    "matched_rule_id": "default",
                    "strict_mode": False,
                },
                "warnings": [],
            },
            "valuation_context": {
                "portfolio_currency": "USD",
                "reporting_currency": "USD",
                "position_basis": "market_value_base",
                "weight_basis": "total_market_value_base",
            },
            "sections": {"positions_baseline": []},
            **source_data_product_runtime_metadata(
                as_of_date=date(2026, 2, 27),
                generated_at=datetime(2026, 2, 27, tzinfo=UTC),
            ),
        }
    )

    mock_integration_service = MagicMock()
    mock_integration_service.get_effective_policy.return_value = EffectiveIntegrationPolicyResponse(
        consumer_system="lotus-gateway",
        tenant_id="default",
        generated_at="2026-02-27T00:00:00Z",
        policy_provenance=PolicyProvenanceMetadata(
            policy_version="tenant-default-v1",
            policy_source="default",
            matched_rule_id="default",
            strict_mode=False,
        ),
        allowed_sections=["POSITIONS_BASELINE"],
        warnings=[],
    )
    mock_integration_service.resolve_benchmark_assignment = AsyncMock(
        return_value={
            "portfolio_id": "PORT-INT-001",
            "benchmark_id": "BMK_GLOBAL_BALANCED_60_40",
            "as_of_date": "2026-01-31",
            "effective_from": "2025-01-01",
            "effective_to": None,
            "assignment_source": "benchmark_policy_engine",
            "assignment_status": "active",
            "policy_pack_id": "policy_pack_wm_v1",
            "source_system": "lotus-manage",
            "assignment_recorded_at": "2026-01-31T09:15:00Z",
            "assignment_version": 3,
            "contract_version": "rfc_062_v1",
            **source_data_product_runtime_metadata(
                as_of_date=date(2026, 1, 31),
                generated_at=datetime(2026, 1, 31, 9, 15, 0, tzinfo=UTC),
            ),
        }
    )

    app.dependency_overrides[get_core_snapshot_service] = lambda: mock_core_snapshot_service
    app.dependency_overrides[get_integration_service] = lambda: mock_integration_service
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield client, mock_core_snapshot_service, mock_integration_service
    app.dependency_overrides.pop(get_core_snapshot_service, None)
    app.dependency_overrides.pop(get_integration_service, None)


async def test_core_snapshot_success(async_test_client):
    client, mock_core_snapshot_service, mock_integration_service = async_test_client

    response = await client.post(
        "/integration/portfolios/PORT-INT-001/core-snapshot",
        json={
            "as_of_date": "2026-02-27",
            "snapshot_mode": "BASELINE",
            "sections": ["positions_baseline"],
            "consumer_system": "lotus-gateway",
            "tenant_id": "default",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["product_name"] == "PortfolioStateSnapshot"
    assert body["product_version"] == "v1"
    assert body["as_of_date"] == "2026-02-27"
    assert body["reconciliation_status"] == "UNKNOWN"
    assert body["data_quality_status"] == "UNKNOWN"
    assert body["governance"]["consumer_system"] == "lotus-gateway"
    mock_integration_service.get_effective_policy.assert_called_once_with(
        consumer_system="lotus-gateway",
        tenant_id="default",
        include_sections=["POSITIONS_BASELINE"],
    )
    mock_core_snapshot_service.get_core_snapshot.assert_awaited_once()


async def test_core_snapshot_policy_block_maps_to_403(async_test_client):
    client, _mock_core_snapshot_service, mock_integration_service = async_test_client
    mock_integration_service.get_effective_policy.return_value = EffectiveIntegrationPolicyResponse(
        consumer_system="lotus-gateway",
        tenant_id="default",
        generated_at="2026-02-27T00:00:00Z",
        policy_provenance=PolicyProvenanceMetadata(
            policy_version="tenant-default-v1",
            policy_source="tenant",
            matched_rule_id="tenant.default",
            strict_mode=True,
        ),
        allowed_sections=[],
        warnings=[],
    )

    response = await client.post(
        "/integration/portfolios/PORT-INT-001/core-snapshot",
        json={
            "as_of_date": "2026-02-27",
            "snapshot_mode": "BASELINE",
            "sections": ["positions_projected"],
            "consumer_system": "lotus-gateway",
            "tenant_id": "default",
        },
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "SNAPSHOT_SECTIONS_BLOCKED_BY_POLICY: positions_projected"


async def test_benchmark_assignment_success(async_test_client):
    client, _mock_core_snapshot_service, mock_integration_service = async_test_client

    response = await client.post(
        "/integration/portfolios/PORT-INT-001/benchmark-assignment",
        json={"as_of_date": "2026-01-31", "reporting_currency": "USD"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["product_name"] == "BenchmarkAssignment"
    assert body["product_version"] == "v1"
    assert body["as_of_date"] == "2026-01-31"
    assert body["benchmark_id"] == "BMK_GLOBAL_BALANCED_60_40"
    assert body["reconciliation_status"] == "UNKNOWN"
    assert body["data_quality_status"] == "UNKNOWN"
    mock_integration_service.resolve_benchmark_assignment.assert_awaited_once()


async def test_benchmark_assignment_not_found_maps_to_404(async_test_client):
    client, _mock_core_snapshot_service, mock_integration_service = async_test_client
    mock_integration_service.resolve_benchmark_assignment = AsyncMock(return_value=None)

    response = await client.post(
        "/integration/portfolios/PORT-INT-001/benchmark-assignment",
        json={"as_of_date": "2026-01-31"},
    )

    assert response.status_code == 404
    assert response.json()["detail"] == (
        "No effective benchmark assignment found for portfolio and as_of_date."
    )
