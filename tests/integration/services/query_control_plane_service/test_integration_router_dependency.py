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
from src.services.query_service.app.services.core_snapshot_service import (
    CoreSnapshotConflictError,
    CoreSnapshotNotFoundError,
    CoreSnapshotUnavailableSectionError,
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
    mock_integration_service.get_benchmark_definition = AsyncMock(
        return_value={
            "benchmark_id": "BMK_GLOBAL_BALANCED_60_40",
            "benchmark_name": "Global Balanced 60/40 (TR)",
            "benchmark_type": "composite",
            "benchmark_currency": "USD",
            "return_convention": "total_return_index",
            "benchmark_status": "active",
            "benchmark_family": "multi_asset_strategic",
            "benchmark_provider": "MSCI",
            "rebalance_frequency": "quarterly",
            "classification_set_id": "wm_global_taxonomy_v1",
            "classification_labels": {"asset_class": "multi_asset", "region": "global"},
            "effective_from": "2025-01-01",
            "effective_to": None,
            "quality_status": "accepted",
            "source_timestamp": "2026-01-31T08:00:00Z",
            "source_vendor": "MSCI",
            "source_record_id": "bmk_60_40_v20260131",
            "components": [
                {
                    "index_id": "IDX_MSCI_WORLD_TR",
                    "composition_weight": "0.6000000000",
                    "composition_effective_from": "2025-01-01",
                    "composition_effective_to": None,
                    "rebalance_event_id": "rebalance_2026q1",
                }
            ],
            "contract_version": "rfc_062_v1",
        }
    )
    mock_integration_service.list_benchmark_catalog = AsyncMock(
        return_value={
            "as_of_date": "2026-01-31",
            "records": [
                {
                    "benchmark_id": "BMK_GLOBAL_BALANCED_60_40",
                    "benchmark_name": "Global Balanced 60/40 (TR)",
                    "benchmark_type": "composite",
                    "benchmark_currency": "USD",
                    "return_convention": "total_return_index",
                    "benchmark_status": "active",
                    "benchmark_family": "multi_asset_strategic",
                    "benchmark_provider": "MSCI",
                    "rebalance_frequency": "quarterly",
                    "classification_set_id": "wm_global_taxonomy_v1",
                    "classification_labels": {"asset_class": "multi_asset", "region": "global"},
                    "effective_from": "2025-01-01",
                    "effective_to": None,
                    "quality_status": "accepted",
                    "source_timestamp": "2026-01-31T08:00:00Z",
                    "source_vendor": "MSCI",
                    "source_record_id": "bmk_60_40_v20260131",
                    "components": [],
                    "contract_version": "rfc_062_v1",
                }
            ],
        }
    )
    mock_integration_service.list_index_catalog = AsyncMock(
        return_value={
            "as_of_date": "2026-01-31",
            "records": [
                {
                    "index_id": "IDX_MSCI_WORLD_TR",
                    "index_name": "MSCI World Total Return",
                    "index_currency": "USD",
                    "index_type": "equity_index",
                    "index_status": "active",
                    "index_provider": "MSCI",
                    "index_market": "global_developed",
                    "classification_set_id": "wm_global_taxonomy_v1",
                    "classification_labels": {
                        "asset_class": "equity",
                        "region": "global",
                        "sector": "broad_market",
                    },
                    "effective_from": "2025-01-01",
                    "effective_to": None,
                    "quality_status": "accepted",
                    "source_timestamp": "2026-01-31T08:00:00Z",
                    "source_vendor": "MSCI",
                    "source_record_id": "idx_world_tr_v20260131",
                    "contract_version": "rfc_062_v1",
                }
            ],
        }
    )
    mock_integration_service.get_risk_free_series = AsyncMock(
        return_value={
            "currency": "USD",
            "as_of_date": "2026-01-31",
            "series_mode": "annualized_rate_series",
            "resolved_window": {"start_date": "2026-01-01", "end_date": "2026-01-31"},
            "frequency": "daily",
            "request_fingerprint": "fp-risk-free-1",
            "points": [],
            "lineage": {"contract_version": "rfc_062_v1", "source_system": "lotus-core"},
            **source_data_product_runtime_metadata(
                as_of_date=date(2026, 1, 31),
                generated_at=datetime(2026, 1, 31, 10, 0, 0, tzinfo=UTC),
            ),
        }
    )
    mock_integration_service.get_benchmark_coverage = AsyncMock(
        return_value={
            "request_fingerprint": "fp-benchmark-coverage-1",
            "observed_start_date": "2026-01-01",
            "observed_end_date": "2026-01-31",
            "expected_start_date": "2026-01-01",
            "expected_end_date": "2026-01-31",
            "total_points": 31,
            "missing_dates_count": 0,
            "missing_dates_sample": [],
            "quality_status_distribution": {"ACCEPTED": 31},
            **source_data_product_runtime_metadata(
                as_of_date=date(2026, 1, 31),
                generated_at=datetime(2026, 1, 31, 10, 0, 0, tzinfo=UTC),
            ),
        }
    )
    mock_integration_service.get_risk_free_coverage = AsyncMock(
        return_value={
            "request_fingerprint": "fp-risk-free-coverage-1",
            "observed_start_date": None,
            "observed_end_date": None,
            "expected_start_date": "2026-01-01",
            "expected_end_date": "2026-01-31",
            "total_points": 0,
            "missing_dates_count": 31,
            "missing_dates_sample": [],
            "quality_status_distribution": {},
            **source_data_product_runtime_metadata(
                as_of_date=date(2026, 1, 31),
                generated_at=datetime(2026, 1, 31, 10, 0, 0, tzinfo=UTC),
            ),
        }
    )
    mock_integration_service.get_classification_taxonomy = AsyncMock(
        return_value={
            "as_of_date": "2026-01-31",
            "records": [],
            "taxonomy_version": "rfc_062_v1",
            "request_fingerprint": "fp-taxonomy-1",
            **source_data_product_runtime_metadata(
                as_of_date=date(2026, 1, 31),
                generated_at=datetime(2026, 1, 31, 10, 0, 0, tzinfo=UTC),
            ),
        }
    )
    mock_integration_service.get_benchmark_composition_window = AsyncMock(
        return_value={
            "benchmark_id": "BMK_GLOBAL_BALANCED_60_40",
            "benchmark_currency": "USD",
            "resolved_window": {"start_date": "2026-01-01", "end_date": "2026-03-31"},
            "segments": [
                {
                    "index_id": "IDX_MSCI_WORLD_TR",
                    "composition_weight": "0.6000000000",
                    "composition_effective_from": "2026-01-01",
                    "composition_effective_to": "2026-03-31",
                    "rebalance_event_id": "rebalance_2026q1",
                }
            ],
            "lineage": {
                "contract_version": "rfc_062_v1",
                "source_system": "lotus-core",
                "generated_by": "query_control_plane_service",
            },
            **source_data_product_runtime_metadata(
                as_of_date=date(2026, 3, 31),
                generated_at=datetime(2026, 3, 31, 10, 0, 0, tzinfo=UTC),
            ),
        }
    )
    mock_integration_service.get_benchmark_market_series = AsyncMock(
        return_value={
            "benchmark_id": "BMK_GLOBAL_BALANCED_60_40",
            "as_of_date": "2026-01-31",
            "benchmark_currency": "USD",
            "target_currency": "EUR",
            "resolved_window": {"start_date": "2026-01-01", "end_date": "2026-01-31"},
            "frequency": "daily",
            "component_series": [
                {
                    "index_id": "IDX_MSCI_WORLD_TR",
                    "points": [
                        {
                            "series_date": "2026-01-02",
                            "series_currency": "USD",
                            "index_price": "100.2500000000",
                            "index_return": "0.0025000000",
                            "component_weight": "0.6000000000",
                            "fx_rate": "0.9200000000",
                            "quality_status": "accepted",
                        }
                    ],
                }
            ],
            "quality_status_summary": {"accepted": 1},
            "fx_context_source_currency": "USD",
            "fx_context_target_currency": "EUR",
            "normalization_policy": "native_component_series_downstream_normalization_required",
            "normalization_status": "native_component_series_with_benchmark_to_target_fx_context",
            "request_fingerprint": "fp-benchmark-market-series-1",
            "page": {
                "page_size": 250,
                "sort_key": "index_id:asc",
                "returned_component_count": 1,
                "request_scope_fingerprint": "fp-benchmark-market-series-1",
                "next_page_token": None,
            },
            "lineage": {
                "contract_version": "rfc_062_v1",
                "source_system": "lotus-core",
                "generated_by": "query_control_plane_service",
            },
            **source_data_product_runtime_metadata(
                as_of_date=date(2026, 1, 31),
                generated_at=datetime(2026, 1, 31, 10, 0, 0, tzinfo=UTC),
            ),
        }
    )
    mock_integration_service.get_index_price_series = AsyncMock(
        return_value={
            "index_id": "IDX_MSCI_WORLD_TR",
            "resolved_window": {"start_date": "2026-01-01", "end_date": "2026-01-31"},
            "frequency": "daily",
            "points": [
                {
                    "series_date": "2026-01-02",
                    "index_price": "100.2500000000",
                    "series_currency": "USD",
                    "value_convention": "close_price",
                    "quality_status": "accepted",
                }
            ],
            "lineage": {
                "contract_version": "rfc_062_v1",
                "source_system": "lotus-core",
            },
            **source_data_product_runtime_metadata(
                as_of_date=date(2026, 1, 31),
                generated_at=datetime(2026, 1, 31, 10, 0, 0, tzinfo=UTC),
            ),
        }
    )
    mock_integration_service.get_index_return_series = AsyncMock(
        return_value={
            "index_id": "IDX_MSCI_WORLD_TR",
            "as_of_date": "2026-01-31",
            "resolved_window": {"start_date": "2026-01-01", "end_date": "2026-01-31"},
            "frequency": "daily",
            "request_fingerprint": "fp-index-return-1",
            "points": [
                {
                    "series_date": "2026-01-02",
                    "index_return": "0.0025000000",
                    "return_period": "1d",
                    "return_convention": "total_return_index",
                    "series_currency": "USD",
                    "quality_status": "accepted",
                }
            ],
            "lineage": {
                "contract_version": "rfc_062_v1",
                "source_system": "lotus-core",
            },
            **source_data_product_runtime_metadata(
                as_of_date=date(2026, 1, 31),
                generated_at=datetime(2026, 1, 31, 10, 0, 0, tzinfo=UTC),
            ),
        }
    )
    mock_integration_service.get_benchmark_return_series = AsyncMock(
        return_value={
            "benchmark_id": "BMK_GLOBAL_BALANCED_60_40",
            "as_of_date": "2026-01-31",
            "resolved_window": {"start_date": "2026-01-01", "end_date": "2026-01-31"},
            "frequency": "daily",
            "request_fingerprint": "fp-benchmark-return-1",
            "points": [
                {
                    "series_date": "2026-01-02",
                    "benchmark_return": "0.0021000000",
                    "return_period": "1d",
                    "return_convention": "total_return_index",
                    "series_currency": "USD",
                    "quality_status": "accepted",
                }
            ],
            "lineage": {
                "contract_version": "rfc_062_v1",
                "source_system": "lotus-core",
            },
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


async def test_core_snapshot_not_found_maps_to_404(async_test_client):
    client, mock_core_snapshot_service, _mock_integration_service = async_test_client
    mock_core_snapshot_service.get_core_snapshot = AsyncMock(
        side_effect=CoreSnapshotNotFoundError("Portfolio or simulation session not found.")
    )

    response = await client.post(
        "/integration/portfolios/PORT-INT-404/core-snapshot",
        json={
            "as_of_date": "2026-02-27",
            "snapshot_mode": "BASELINE",
            "sections": ["positions_baseline"],
            "consumer_system": "lotus-gateway",
            "tenant_id": "default",
        },
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Portfolio or simulation session not found."


async def test_core_snapshot_conflict_maps_to_409(async_test_client):
    client, mock_core_snapshot_service, _mock_integration_service = async_test_client
    mock_core_snapshot_service.get_core_snapshot = AsyncMock(
        side_effect=CoreSnapshotConflictError(
            "Simulation expected_version mismatch or portfolio/session conflict."
        )
    )

    response = await client.post(
        "/integration/portfolios/PORT-INT-001/core-snapshot",
        json={
            "as_of_date": "2026-02-27",
            "snapshot_mode": "SIMULATION",
            "sections": ["positions_baseline"],
            "consumer_system": "lotus-gateway",
            "tenant_id": "default",
            "simulation": {"session_id": "SIM-20260310-0001", "expected_version": 3},
        },
    )

    assert response.status_code == 409
    assert (
        response.json()["detail"]
        == "Simulation expected_version mismatch or portfolio/session conflict."
    )


async def test_core_snapshot_unavailable_section_maps_to_422(async_test_client):
    client, mock_core_snapshot_service, _mock_integration_service = async_test_client
    mock_core_snapshot_service.get_core_snapshot = AsyncMock(
        side_effect=CoreSnapshotUnavailableSectionError(
            "Section cannot be fulfilled due to missing valuation dependencies."
        )
    )

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

    assert response.status_code == 422
    assert (
        response.json()["detail"]
        == "Section cannot be fulfilled due to missing valuation dependencies."
    )


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
    mock_integration_service.resolve_benchmark_assignment.assert_awaited_once_with(
        portfolio_id="PORT-INT-001",
        as_of_date=date(2026, 1, 31),
    )


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


async def test_benchmark_definition_success(async_test_client):
    client, _mock_core_snapshot_service, mock_integration_service = async_test_client

    response = await client.post(
        "/integration/benchmarks/BMK_GLOBAL_BALANCED_60_40/definition",
        json={"as_of_date": "2026-01-31"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["benchmark_id"] == "BMK_GLOBAL_BALANCED_60_40"
    assert body["benchmark_name"] == "Global Balanced 60/40 (TR)"
    assert body["benchmark_type"] == "composite"
    assert body["components"][0]["index_id"] == "IDX_MSCI_WORLD_TR"
    mock_integration_service.get_benchmark_definition.assert_awaited_once_with(
        "BMK_GLOBAL_BALANCED_60_40",
        date(2026, 1, 31),
    )


async def test_benchmark_definition_not_found_maps_to_404(async_test_client):
    client, _mock_core_snapshot_service, mock_integration_service = async_test_client
    mock_integration_service.get_benchmark_definition = AsyncMock(return_value=None)

    response = await client.post(
        "/integration/benchmarks/BMK_GLOBAL_BALANCED_60_40/definition",
        json={"as_of_date": "2026-01-31"},
    )

    assert response.status_code == 404
    assert response.json()["detail"] == (
        "No effective benchmark definition found for benchmark_id and as_of_date."
    )


async def test_benchmark_catalog_success(async_test_client):
    client, _mock_core_snapshot_service, mock_integration_service = async_test_client

    response = await client.post(
        "/integration/benchmarks/catalog",
        json={
            "as_of_date": "2026-01-31",
            "benchmark_type": "composite",
            "benchmark_currency": "USD",
            "benchmark_status": "active",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["as_of_date"] == "2026-01-31"
    assert body["records"][0]["benchmark_id"] == "BMK_GLOBAL_BALANCED_60_40"
    assert body["records"][0]["benchmark_type"] == "composite"
    mock_integration_service.list_benchmark_catalog.assert_awaited_once_with(
        as_of_date=date(2026, 1, 31),
        benchmark_type="composite",
        benchmark_currency="USD",
        benchmark_status="active",
    )


async def test_index_catalog_success(async_test_client):
    client, _mock_core_snapshot_service, mock_integration_service = async_test_client

    response = await client.post(
        "/integration/indices/catalog",
        json={
            "as_of_date": "2026-01-31",
            "index_currency": "USD",
            "index_type": "equity_index",
            "index_status": "active",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["as_of_date"] == "2026-01-31"
    assert body["records"][0]["index_id"] == "IDX_MSCI_WORLD_TR"
    assert body["records"][0]["index_type"] == "equity_index"
    mock_integration_service.list_index_catalog.assert_awaited_once_with(
        as_of_date=date(2026, 1, 31),
        index_currency="USD",
        index_type="equity_index",
        index_status="active",
    )


async def test_benchmark_composition_window_success(async_test_client):
    client, _mock_core_snapshot_service, mock_integration_service = async_test_client

    response = await client.post(
        "/integration/benchmarks/BMK_GLOBAL_BALANCED_60_40/composition-window",
        json={"window": {"start_date": "2026-01-01", "end_date": "2026-03-31"}},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["product_name"] == "BenchmarkConstituentWindow"
    assert body["product_version"] == "v1"
    assert body["benchmark_id"] == "BMK_GLOBAL_BALANCED_60_40"
    assert body["benchmark_currency"] == "USD"
    assert body["segments"][0]["index_id"] == "IDX_MSCI_WORLD_TR"
    assert body["reconciliation_status"] == "UNKNOWN"
    assert body["data_quality_status"] == "UNKNOWN"
    mock_integration_service.get_benchmark_composition_window.assert_awaited_once()
    composition_call = mock_integration_service.get_benchmark_composition_window.await_args.kwargs
    assert composition_call["benchmark_id"] == "BMK_GLOBAL_BALANCED_60_40"
    assert composition_call["request"].window.start_date == date(2026, 1, 1)
    assert composition_call["request"].window.end_date == date(2026, 3, 31)


async def test_benchmark_composition_window_not_found_maps_to_404(async_test_client):
    client, _mock_core_snapshot_service, mock_integration_service = async_test_client
    mock_integration_service.get_benchmark_composition_window = AsyncMock(return_value=None)

    response = await client.post(
        "/integration/benchmarks/BMK_GLOBAL_BALANCED_60_40/composition-window",
        json={"window": {"start_date": "2026-01-01", "end_date": "2026-03-31"}},
    )

    assert response.status_code == 404
    assert response.json()["detail"] == (
        "No overlapping benchmark definition found for benchmark_id and requested window."
    )


async def test_benchmark_market_series_success(async_test_client):
    client, _mock_core_snapshot_service, mock_integration_service = async_test_client

    response = await client.post(
        "/integration/benchmarks/BMK_GLOBAL_BALANCED_60_40/market-series",
        json={
            "as_of_date": "2026-01-31",
            "window": {"start_date": "2026-01-01", "end_date": "2026-01-31"},
            "frequency": "daily",
            "target_currency": "EUR",
            "series_fields": ["index_price", "index_return", "component_weight", "fx_rate"],
            "page": {"page_size": 250},
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["product_name"] == "MarketDataWindow"
    assert body["product_version"] == "v1"
    assert body["benchmark_id"] == "BMK_GLOBAL_BALANCED_60_40"
    assert body["benchmark_currency"] == "USD"
    assert body["target_currency"] == "EUR"
    assert body["normalization_policy"] == (
        "native_component_series_downstream_normalization_required"
    )
    assert body["page"]["returned_component_count"] == 1
    assert body["component_series"][0]["points"][0]["fx_rate"] == "0.9200000000"
    assert body["reconciliation_status"] == "UNKNOWN"
    assert body["data_quality_status"] == "UNKNOWN"
    mock_integration_service.get_benchmark_market_series.assert_awaited_once()
    market_call = mock_integration_service.get_benchmark_market_series.await_args.kwargs
    assert market_call["benchmark_id"] == "BMK_GLOBAL_BALANCED_60_40"
    assert market_call["request"].as_of_date == date(2026, 1, 31)
    assert market_call["request"].window.start_date == date(2026, 1, 1)
    assert market_call["request"].window.end_date == date(2026, 1, 31)
    assert market_call["request"].target_currency == "EUR"
    assert market_call["request"].series_fields == [
        "index_price",
        "index_return",
        "component_weight",
        "fx_rate",
    ]
    assert market_call["request"].page.page_size == 250


async def test_benchmark_market_series_invalid_page_token_maps_to_400(async_test_client):
    client, _mock_core_snapshot_service, mock_integration_service = async_test_client
    mock_integration_service.get_benchmark_market_series = AsyncMock(
        side_effect=ValueError("Invalid benchmark market series page_token.")
    )

    response = await client.post(
        "/integration/benchmarks/BMK_GLOBAL_BALANCED_60_40/market-series",
        json={
            "as_of_date": "2026-01-31",
            "window": {"start_date": "2026-01-01", "end_date": "2026-01-31"},
            "frequency": "daily",
            "target_currency": "EUR",
            "series_fields": ["index_price", "fx_rate"],
            "page": {"page_size": 250, "page_token": "invalid-token"},
        },
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Invalid benchmark market series page_token."


async def test_index_price_series_success(async_test_client):
    client, _mock_core_snapshot_service, mock_integration_service = async_test_client

    response = await client.post(
        "/integration/indices/IDX_MSCI_WORLD_TR/price-series",
        json={
            "as_of_date": "2026-01-31",
            "window": {"start_date": "2026-01-01", "end_date": "2026-01-31"},
            "frequency": "daily",
            "target_currency": "USD",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["product_name"] == "IndexSeriesWindow"
    assert body["product_version"] == "v1"
    assert body["index_id"] == "IDX_MSCI_WORLD_TR"
    assert body["points"][0]["index_price"] == "100.2500000000"
    assert body["reconciliation_status"] == "UNKNOWN"
    assert body["data_quality_status"] == "UNKNOWN"
    mock_integration_service.get_index_price_series.assert_awaited_once()


async def test_index_return_series_success(async_test_client):
    client, _mock_core_snapshot_service, mock_integration_service = async_test_client

    response = await client.post(
        "/integration/indices/IDX_MSCI_WORLD_TR/return-series",
        json={
            "as_of_date": "2026-01-31",
            "window": {"start_date": "2026-01-01", "end_date": "2026-01-31"},
            "frequency": "daily",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["product_name"] == "IndexSeriesWindow"
    assert body["product_version"] == "v1"
    assert body["index_id"] == "IDX_MSCI_WORLD_TR"
    assert body["request_fingerprint"] == "fp-index-return-1"
    assert body["points"][0]["return_convention"] == "total_return_index"
    assert body["points"][0]["index_return"] == "0.0025000000"
    assert body["reconciliation_status"] == "UNKNOWN"
    assert body["data_quality_status"] == "UNKNOWN"
    mock_integration_service.get_index_return_series.assert_awaited_once()


async def test_benchmark_return_series_success(async_test_client):
    client, _mock_core_snapshot_service, mock_integration_service = async_test_client

    response = await client.post(
        "/integration/benchmarks/BMK_GLOBAL_BALANCED_60_40/return-series",
        json={
            "as_of_date": "2026-01-31",
            "window": {"start_date": "2026-01-01", "end_date": "2026-01-31"},
            "frequency": "daily",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["benchmark_id"] == "BMK_GLOBAL_BALANCED_60_40"
    assert body["request_fingerprint"] == "fp-benchmark-return-1"
    assert body["points"][0]["benchmark_return"] == "0.0021000000"
    mock_integration_service.get_benchmark_return_series.assert_awaited_once()
    benchmark_return_call = mock_integration_service.get_benchmark_return_series.await_args.kwargs
    assert benchmark_return_call["benchmark_id"] == "BMK_GLOBAL_BALANCED_60_40"
    assert benchmark_return_call["request"].as_of_date == date(2026, 1, 31)
    assert benchmark_return_call["request"].window.start_date == date(2026, 1, 1)
    assert benchmark_return_call["request"].window.end_date == date(2026, 1, 31)
    assert benchmark_return_call["request"].frequency == "daily"


async def test_risk_free_series_success(async_test_client):
    client, _mock_core_snapshot_service, mock_integration_service = async_test_client

    response = await client.post(
        "/integration/reference/risk-free-series",
        json={
            "as_of_date": "2026-01-31",
            "window": {"start_date": "2026-01-01", "end_date": "2026-01-31"},
            "frequency": "daily",
            "currency": "USD",
            "series_mode": "annualized_rate_series",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["product_name"] == "RiskFreeSeriesWindow"
    assert body["product_version"] == "v1"
    assert body["currency"] == "USD"
    assert body["as_of_date"] == "2026-01-31"
    assert body["reconciliation_status"] == "UNKNOWN"
    assert body["data_quality_status"] == "UNKNOWN"
    mock_integration_service.get_risk_free_series.assert_awaited_once()


async def test_benchmark_coverage_success(async_test_client):
    client, _mock_core_snapshot_service, mock_integration_service = async_test_client

    response = await client.post(
        "/integration/benchmarks/BMK_GLOBAL_BALANCED_60_40/coverage",
        json={"window": {"start_date": "2026-01-01", "end_date": "2026-01-31"}},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["product_name"] == "DataQualityCoverageReport"
    assert body["product_version"] == "v1"
    assert body["observed_start_date"] == "2026-01-01"
    assert body["observed_end_date"] == "2026-01-31"
    assert body["total_points"] == 31
    assert body["missing_dates_count"] == 0
    assert body["quality_status_distribution"] == {"ACCEPTED": 31}
    assert body["reconciliation_status"] == "UNKNOWN"
    assert body["data_quality_status"] == "UNKNOWN"
    mock_integration_service.get_benchmark_coverage.assert_awaited_once_with(
        benchmark_id="BMK_GLOBAL_BALANCED_60_40",
        start_date=date(2026, 1, 1),
        end_date=date(2026, 1, 31),
    )


async def test_risk_free_coverage_success(async_test_client):
    client, _mock_core_snapshot_service, mock_integration_service = async_test_client

    response = await client.post(
        "/integration/reference/risk-free-series/coverage?currency=USD",
        json={"window": {"start_date": "2026-01-01", "end_date": "2026-01-31"}},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["product_name"] == "DataQualityCoverageReport"
    assert body["product_version"] == "v1"
    assert body["total_points"] == 0
    assert body["missing_dates_count"] == 31
    assert body["reconciliation_status"] == "UNKNOWN"
    assert body["data_quality_status"] == "UNKNOWN"
    mock_integration_service.get_risk_free_coverage.assert_awaited_once_with(
        currency="USD",
        start_date=date(2026, 1, 1),
        end_date=date(2026, 1, 31),
    )


async def test_classification_taxonomy_success(async_test_client):
    client, _mock_core_snapshot_service, mock_integration_service = async_test_client

    response = await client.post(
        "/integration/reference/classification-taxonomy",
        json={"as_of_date": "2026-01-31"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["product_name"] == "InstrumentReferenceBundle"
    assert body["product_version"] == "v1"
    assert body["as_of_date"] == "2026-01-31"
    assert body["taxonomy_version"] == "rfc_062_v1"
    assert body["request_fingerprint"] == "fp-taxonomy-1"
    assert body["reconciliation_status"] == "UNKNOWN"
    assert body["data_quality_status"] == "UNKNOWN"
    mock_integration_service.get_classification_taxonomy.assert_awaited_once_with(
        as_of_date=date(2026, 1, 31),
        taxonomy_scope=None,
    )


async def test_classification_taxonomy_scope_filter_success(async_test_client):
    client, _mock_core_snapshot_service, mock_integration_service = async_test_client
    mock_integration_service.get_classification_taxonomy = AsyncMock(
        return_value={
            "as_of_date": "2026-01-31",
            "records": [
                {
                    "classification_set_id": "wm_global_taxonomy_v1",
                    "taxonomy_scope": "index",
                    "dimension_name": "sector",
                    "dimension_value": "technology",
                    "dimension_description": "Technology sector classification",
                    "effective_from": "2025-01-01",
                    "effective_to": None,
                    "quality_status": "accepted",
                }
            ],
            "taxonomy_version": "rfc_062_v1",
            "request_fingerprint": "fp-taxonomy-index-1",
            **source_data_product_runtime_metadata(
                as_of_date=date(2026, 1, 31),
                generated_at=datetime(2026, 1, 31, 10, 0, 0, tzinfo=UTC),
            ),
        }
    )

    response = await client.post(
        "/integration/reference/classification-taxonomy",
        json={"as_of_date": "2026-01-31", "taxonomy_scope": "index"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["taxonomy_version"] == "rfc_062_v1"
    assert body["request_fingerprint"] == "fp-taxonomy-index-1"
    assert body["records"][0]["taxonomy_scope"] == "index"
    assert body["records"][0]["dimension_name"] == "sector"
    mock_integration_service.get_classification_taxonomy.assert_awaited_once_with(
        as_of_date=date(2026, 1, 31),
        taxonomy_scope="index",
    )
