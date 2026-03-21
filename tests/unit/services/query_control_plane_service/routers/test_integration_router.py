from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

from src.services.query_control_plane_service.app.routers.integration import (
    create_core_snapshot,
    fetch_benchmark_catalog,
    fetch_benchmark_composition_window,
    fetch_benchmark_definition,
    fetch_benchmark_market_series,
    fetch_benchmark_return_series,
    fetch_classification_taxonomy,
    fetch_index_catalog,
    fetch_index_price_series,
    fetch_index_return_series,
    fetch_risk_free_series,
    get_benchmark_coverage,
    get_core_snapshot_service,
    get_effective_integration_policy,
    get_instrument_enrichment_bulk,
    get_integration_service,
    get_risk_free_coverage,
    resolve_portfolio_benchmark_assignment,
)
from src.services.query_service.app.dtos.core_snapshot_dto import (
    CoreSnapshotMode,
    CoreSnapshotRequest,
    CoreSnapshotSection,
)
from src.services.query_service.app.dtos.integration_dto import (
    EffectiveIntegrationPolicyResponse,
    InstrumentEnrichmentBulkRequest,
    PolicyProvenanceMetadata,
)
from src.services.query_service.app.dtos.reference_integration_dto import (
    BenchmarkAssignmentRequest,
    BenchmarkCatalogRequest,
    BenchmarkCompositionWindowRequest,
    BenchmarkDefinitionRequest,
    BenchmarkMarketSeriesRequest,
    BenchmarkReturnSeriesRequest,
    ClassificationTaxonomyRequest,
    CoverageRequest,
    IndexCatalogRequest,
    IndexSeriesRequest,
    IntegrationWindow,
    RiskFreeSeriesRequest,
)
from src.services.query_service.app.services.core_snapshot_service import (
    CoreSnapshotBadRequestError,
    CoreSnapshotConflictError,
    CoreSnapshotNotFoundError,
    CoreSnapshotService,
    CoreSnapshotUnavailableSectionError,
)
from src.services.query_service.app.services.integration_service import IntegrationService


@pytest.mark.asyncio
async def test_get_effective_integration_policy_router_function() -> None:
    mock_service = MagicMock(spec=IntegrationService)
    mock_service.get_effective_policy.return_value = {
        "contract_version": "v1",
        "source_service": "lotus-core",
        "consumer_system": "lotus-manage",
        "tenant_id": "tenant-a",
        "generated_at": "2026-02-27T00:00:00Z",
        "policy_provenance": {
            "policy_version": "tenant-default-v1",
            "policy_source": "default",
            "matched_rule_id": "default",
            "strict_mode": False,
        },
        "allowed_sections": ["OVERVIEW"],
        "warnings": [],
    }

    response = await get_effective_integration_policy(
        consumer_system="lotus-manage",
        tenant_id="tenant-a",
        include_sections=["OVERVIEW"],
        integration_service=mock_service,
    )

    mock_service.get_effective_policy.assert_called_once_with(
        consumer_system="lotus-manage",
        tenant_id="tenant-a",
        include_sections=["OVERVIEW"],
    )
    assert response["consumer_system"] == "lotus-manage"


def test_get_integration_service_factory_returns_service() -> None:
    service = get_integration_service(db=MagicMock())
    assert isinstance(service, IntegrationService)


def test_get_core_snapshot_service_factory_returns_service() -> None:
    service = get_core_snapshot_service(db=MagicMock())
    assert isinstance(service, CoreSnapshotService)


@pytest.mark.asyncio
async def test_create_core_snapshot_router_function() -> None:
    mock_service = MagicMock(spec=CoreSnapshotService)
    mock_integration_service = MagicMock(spec=IntegrationService)
    mock_integration_service.get_effective_policy.return_value = EffectiveIntegrationPolicyResponse(
        consumer_system="lotus-performance",
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
    request = CoreSnapshotRequest(
        as_of_date="2026-02-27",
        snapshot_mode=CoreSnapshotMode.BASELINE,
        sections=[CoreSnapshotSection.POSITIONS_BASELINE],
        consumer_system="lotus-performance",
        tenant_id="default",
    )
    mock_service.get_core_snapshot.return_value = {
        "portfolio_id": "PORT_001",
        "as_of_date": "2026-02-27",
        "snapshot_mode": "BASELINE",
        "generated_at": "2026-02-27T00:00:00Z",
        "contract_version": "rfc_081_v1",
        "request_fingerprint": "fp-core-001",
        "freshness": {
            "freshness_status": "CURRENT_SNAPSHOT",
            "baseline_source": "position_state",
            "snapshot_timestamp": None,
            "snapshot_epoch": None,
            "fallback_reason": None,
        },
        "governance": {
            "consumer_system": "lotus-performance",
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
    }

    response = await create_core_snapshot(
        portfolio_id="PORT_001",
        request=request,
        service=mock_service,
        integration_service=mock_integration_service,
    )

    mock_service.get_core_snapshot.assert_called_once()
    assert response["portfolio_id"] == "PORT_001"
    mock_integration_service.get_effective_policy.assert_called_once_with(
        consumer_system="lotus-performance",
        tenant_id="default",
        include_sections=["POSITIONS_BASELINE"],
    )


@pytest.mark.asyncio
async def test_create_core_snapshot_maps_not_found_to_404() -> None:
    mock_service = MagicMock(spec=CoreSnapshotService)
    mock_integration_service = MagicMock(spec=IntegrationService)
    mock_integration_service.get_effective_policy.return_value = EffectiveIntegrationPolicyResponse(
        consumer_system="lotus-performance",
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
    request = CoreSnapshotRequest(
        as_of_date="2026-02-27",
        snapshot_mode=CoreSnapshotMode.BASELINE,
        sections=[CoreSnapshotSection.POSITIONS_BASELINE],
        consumer_system="lotus-performance",
        tenant_id="default",
    )
    mock_service.get_core_snapshot.side_effect = CoreSnapshotNotFoundError("not found")

    with pytest.raises(HTTPException) as exc_info:
        await create_core_snapshot(
            portfolio_id="PORT_404",
            request=request,
            service=mock_service,
            integration_service=mock_integration_service,
        )

    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_create_core_snapshot_maps_bad_request_to_400() -> None:
    mock_service = MagicMock(spec=CoreSnapshotService)
    mock_integration_service = MagicMock(spec=IntegrationService)
    mock_integration_service.get_effective_policy.return_value = EffectiveIntegrationPolicyResponse(
        consumer_system="lotus-performance",
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
    request = CoreSnapshotRequest(
        as_of_date="2026-02-27",
        snapshot_mode=CoreSnapshotMode.BASELINE,
        sections=[CoreSnapshotSection.POSITIONS_BASELINE],
        consumer_system="lotus-performance",
        tenant_id="default",
    )
    mock_service.get_core_snapshot.side_effect = CoreSnapshotBadRequestError("bad")

    with pytest.raises(HTTPException) as exc_info:
        await create_core_snapshot(
            portfolio_id="PORT_001",
            request=request,
            service=mock_service,
            integration_service=mock_integration_service,
        )

    assert exc_info.value.status_code == 400


@pytest.mark.asyncio
async def test_create_core_snapshot_maps_conflict_to_409() -> None:
    mock_service = MagicMock(spec=CoreSnapshotService)
    mock_integration_service = MagicMock(spec=IntegrationService)
    mock_integration_service.get_effective_policy.return_value = EffectiveIntegrationPolicyResponse(
        consumer_system="lotus-performance",
        tenant_id="default",
        generated_at="2026-02-27T00:00:00Z",
        policy_provenance=PolicyProvenanceMetadata(
            policy_version="tenant-default-v1",
            policy_source="default",
            matched_rule_id="default",
            strict_mode=False,
        ),
        allowed_sections=["POSITIONS_PROJECTED"],
        warnings=[],
    )
    request = CoreSnapshotRequest(
        as_of_date="2026-02-27",
        snapshot_mode=CoreSnapshotMode.SIMULATION,
        sections=[CoreSnapshotSection.POSITIONS_PROJECTED],
        simulation={"session_id": "SIM_1"},
        consumer_system="lotus-performance",
        tenant_id="default",
    )
    mock_service.get_core_snapshot.side_effect = CoreSnapshotConflictError("conflict")

    with pytest.raises(HTTPException) as exc_info:
        await create_core_snapshot(
            portfolio_id="PORT_001",
            request=request,
            service=mock_service,
            integration_service=mock_integration_service,
        )

    assert exc_info.value.status_code == 409


@pytest.mark.asyncio
async def test_create_core_snapshot_maps_unavailable_section_to_422() -> None:
    mock_service = MagicMock(spec=CoreSnapshotService)
    mock_integration_service = MagicMock(spec=IntegrationService)
    mock_integration_service.get_effective_policy.return_value = EffectiveIntegrationPolicyResponse(
        consumer_system="lotus-performance",
        tenant_id="default",
        generated_at="2026-02-27T00:00:00Z",
        policy_provenance=PolicyProvenanceMetadata(
            policy_version="tenant-default-v1",
            policy_source="default",
            matched_rule_id="default",
            strict_mode=False,
        ),
        allowed_sections=["POSITIONS_PROJECTED"],
        warnings=[],
    )
    request = CoreSnapshotRequest(
        as_of_date="2026-02-27",
        snapshot_mode=CoreSnapshotMode.SIMULATION,
        sections=[CoreSnapshotSection.POSITIONS_PROJECTED],
        simulation={"session_id": "SIM_1"},
        consumer_system="lotus-performance",
        tenant_id="default",
    )
    mock_service.get_core_snapshot.side_effect = CoreSnapshotUnavailableSectionError("missing")

    with pytest.raises(HTTPException) as exc_info:
        await create_core_snapshot(
            portfolio_id="PORT_001",
            request=request,
            service=mock_service,
            integration_service=mock_integration_service,
        )

    assert exc_info.value.status_code == 422


@pytest.mark.asyncio
async def test_create_core_snapshot_maps_policy_block_to_403() -> None:
    mock_service = MagicMock(spec=CoreSnapshotService)
    mock_integration_service = MagicMock(spec=IntegrationService)
    mock_integration_service.get_effective_policy.return_value = EffectiveIntegrationPolicyResponse(
        consumer_system="lotus-performance",
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
    request = CoreSnapshotRequest(
        as_of_date="2026-02-27",
        snapshot_mode=CoreSnapshotMode.BASELINE,
        sections=[CoreSnapshotSection.POSITIONS_BASELINE],
        consumer_system="lotus-performance",
        tenant_id="default",
    )

    with pytest.raises(HTTPException) as exc_info:
        await create_core_snapshot(
            portfolio_id="PORT_001",
            request=request,
            service=mock_service,
            integration_service=mock_integration_service,
        )

    assert exc_info.value.status_code == 403


@pytest.mark.asyncio
async def test_create_core_snapshot_filters_sections_in_non_strict_mode() -> None:
    mock_service = MagicMock(spec=CoreSnapshotService)
    mock_service.get_core_snapshot.return_value = {
        "portfolio_id": "PORT_001",
        "as_of_date": "2026-02-27",
        "snapshot_mode": "BASELINE",
        "generated_at": "2026-02-27T00:00:00Z",
        "contract_version": "rfc_081_v1",
        "request_fingerprint": "fp-core-002",
        "freshness": {
            "freshness_status": "CURRENT_SNAPSHOT",
            "baseline_source": "position_state",
            "snapshot_timestamp": None,
            "snapshot_epoch": None,
            "fallback_reason": None,
        },
        "governance": {
            "consumer_system": "lotus-performance",
            "tenant_id": "default",
            "requested_sections": ["positions_baseline", "portfolio_totals"],
            "applied_sections": ["positions_baseline"],
            "dropped_sections": ["portfolio_totals"],
            "policy_provenance": {
                "policy_version": "tenant-default-v1",
                "policy_source": "tenant",
                "matched_rule_id": "tenant.default",
                "strict_mode": False,
            },
            "warnings": ["SECTIONS_DROPPED_NON_STRICT_MODE"],
        },
        "valuation_context": {
            "portfolio_currency": "USD",
            "reporting_currency": "USD",
            "position_basis": "market_value_base",
            "weight_basis": "total_market_value_base",
        },
        "sections": {"positions_baseline": []},
    }

    mock_integration_service = MagicMock(spec=IntegrationService)
    mock_integration_service.get_effective_policy.return_value = EffectiveIntegrationPolicyResponse(
        consumer_system="lotus-performance",
        tenant_id="default",
        generated_at="2026-02-27T00:00:00Z",
        policy_provenance=PolicyProvenanceMetadata(
            policy_version="tenant-default-v1",
            policy_source="tenant",
            matched_rule_id="tenant.default",
            strict_mode=False,
        ),
        allowed_sections=["POSITIONS_BASELINE"],
        warnings=[],
    )

    request = CoreSnapshotRequest(
        as_of_date="2026-02-27",
        snapshot_mode=CoreSnapshotMode.BASELINE,
        sections=[CoreSnapshotSection.POSITIONS_BASELINE, CoreSnapshotSection.PORTFOLIO_TOTALS],
        consumer_system="lotus-performance",
        tenant_id="default",
    )

    await create_core_snapshot(
        portfolio_id="PORT_001",
        request=request,
        service=mock_service,
        integration_service=mock_integration_service,
    )

    called_request = mock_service.get_core_snapshot.call_args.kwargs["request"]
    assert called_request.sections == [CoreSnapshotSection.POSITIONS_BASELINE]


@pytest.mark.asyncio
async def test_get_instrument_enrichment_bulk_router_function() -> None:
    mock_service = MagicMock(spec=CoreSnapshotService)
    mock_service.get_instrument_enrichment_bulk.return_value = [
        {
            "security_id": "SEC_AAPL_US",
            "issuer_id": "ISSUER_APPLE_INC",
            "issuer_name": "Apple Inc.",
            "ultimate_parent_issuer_id": "ISSUER_APPLE_HOLDING",
            "ultimate_parent_issuer_name": "Apple Holdings PLC",
        }
    ]

    response = await get_instrument_enrichment_bulk(
        request=InstrumentEnrichmentBulkRequest(security_ids=["SEC_AAPL_US"]),
        service=mock_service,
    )

    assert response.records[0].security_id == "SEC_AAPL_US"
    mock_service.get_instrument_enrichment_bulk.assert_called_once_with(["SEC_AAPL_US"])


@pytest.mark.asyncio
async def test_get_instrument_enrichment_bulk_maps_bad_request_to_400() -> None:
    mock_service = MagicMock(spec=CoreSnapshotService)
    mock_service.get_instrument_enrichment_bulk.side_effect = CoreSnapshotBadRequestError("bad")

    with pytest.raises(HTTPException) as exc_info:
        await get_instrument_enrichment_bulk(
            request=InstrumentEnrichmentBulkRequest(security_ids=["SEC_AAPL_US"]),
            service=mock_service,
        )

    assert exc_info.value.status_code == 400


@pytest.mark.asyncio
async def test_resolve_portfolio_benchmark_assignment_maps_not_found_to_404() -> None:
    mock_service = MagicMock(spec=IntegrationService)
    mock_service.resolve_benchmark_assignment = AsyncMock(return_value=None)

    with pytest.raises(HTTPException) as exc_info:
        await resolve_portfolio_benchmark_assignment(
            portfolio_id="DEMO_DPM_EUR_001",
            request=BenchmarkAssignmentRequest(as_of_date="2026-01-31"),
            integration_service=mock_service,
        )

    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_resolve_portfolio_benchmark_assignment_success_path() -> None:
    mock_service = MagicMock(spec=IntegrationService)
    mock_service.resolve_benchmark_assignment = AsyncMock(
        return_value={
            "portfolio_id": "DEMO_DPM_EUR_001",
            "benchmark_id": "BMK_GLOBAL_BALANCED_60_40",
            "as_of_date": "2026-01-31",
            "source": "portfolio_assignment",
            "quality_status": "accepted",
        }
    )

    response = await resolve_portfolio_benchmark_assignment(
        portfolio_id="DEMO_DPM_EUR_001",
        request=BenchmarkAssignmentRequest(as_of_date="2026-01-31"),
        integration_service=mock_service,
    )

    assert response["portfolio_id"] == "DEMO_DPM_EUR_001"
    assert response["benchmark_id"] == "BMK_GLOBAL_BALANCED_60_40"


@pytest.mark.asyncio
async def test_fetch_benchmark_and_index_catalog_router_functions() -> None:
    mock_service = MagicMock(spec=IntegrationService)
    mock_service.list_benchmark_catalog = AsyncMock(
        return_value={"as_of_date": "2026-01-31", "records": []}
    )
    mock_service.list_index_catalog = AsyncMock(
        return_value={"as_of_date": "2026-01-31", "records": []}
    )

    benchmark_response = await fetch_benchmark_catalog(
        request=BenchmarkCatalogRequest(as_of_date="2026-01-31"),
        integration_service=mock_service,
    )
    index_response = await fetch_index_catalog(
        request=IndexCatalogRequest(as_of_date="2026-01-31"),
        integration_service=mock_service,
    )

    assert benchmark_response["records"] == []
    assert index_response["records"] == []


@pytest.mark.asyncio
async def test_fetch_benchmark_definition_and_coverage_router_functions() -> None:
    mock_service = MagicMock(spec=IntegrationService)
    mock_service.get_benchmark_definition = AsyncMock(
        return_value={
            "benchmark_id": "BMK_GLOBAL_BALANCED_60_40",
            "benchmark_name": "Global Balanced 60/40 (TR)",
            "benchmark_type": "composite",
            "benchmark_currency": "USD",
            "return_convention": "total_return_index",
            "benchmark_status": "active",
            "benchmark_family": None,
            "benchmark_provider": "MSCI",
            "rebalance_frequency": "quarterly",
            "classification_set_id": None,
            "classification_labels": {},
            "effective_from": "2025-01-01",
            "effective_to": None,
            "quality_status": "accepted",
            "source_timestamp": None,
            "source_vendor": "MSCI",
            "source_record_id": "bmk_v20260131",
            "components": [],
            "contract_version": "rfc_062_v1",
        }
    )
    mock_service.get_benchmark_coverage = AsyncMock(
        return_value={
            "observed_start_date": "2026-01-01",
            "observed_end_date": "2026-01-31",
            "expected_start_date": "2026-01-01",
            "expected_end_date": "2026-01-31",
            "total_points": 31,
            "missing_dates_count": 0,
            "missing_dates_sample": [],
            "quality_status_distribution": {"accepted": 31},
        }
    )

    definition_response = await fetch_benchmark_definition(
        benchmark_id="BMK_GLOBAL_BALANCED_60_40",
        request=BenchmarkDefinitionRequest(as_of_date="2026-01-31"),
        integration_service=mock_service,
    )
    coverage_response = await get_benchmark_coverage(
        benchmark_id="BMK_GLOBAL_BALANCED_60_40",
        request=CoverageRequest(
            window=IntegrationWindow(start_date="2026-01-01", end_date="2026-01-31")
        ),
        integration_service=mock_service,
    )

    assert definition_response["benchmark_id"] == "BMK_GLOBAL_BALANCED_60_40"
    assert coverage_response["total_points"] == 31


@pytest.mark.asyncio
async def test_fetch_benchmark_composition_window_router_functions() -> None:
    mock_service = MagicMock(spec=IntegrationService)
    mock_service.get_benchmark_composition_window = AsyncMock(
        return_value={
            "benchmark_id": "BMK_GLOBAL_BALANCED_60_40",
            "benchmark_currency": "USD",
            "resolved_window": {"start_date": "2026-01-01", "end_date": "2026-03-31"},
            "segments": [
                {
                    "index_id": "IDX_US_EQ",
                    "composition_weight": "0.6000000000",
                    "composition_effective_from": "2026-01-01",
                    "composition_effective_to": "2026-03-31",
                    "rebalance_event_id": "rebalance_2026q1",
                }
            ],
            "lineage": {"contract_version": "rfc_062_v1"},
        }
    )

    response = await fetch_benchmark_composition_window(
        benchmark_id="BMK_GLOBAL_BALANCED_60_40",
        request=BenchmarkCompositionWindowRequest(
            window=IntegrationWindow(start_date="2026-01-01", end_date="2026-03-31")
        ),
        integration_service=mock_service,
    )

    assert response["benchmark_id"] == "BMK_GLOBAL_BALANCED_60_40"
    assert response["segments"][0]["index_id"] == "IDX_US_EQ"


@pytest.mark.asyncio
async def test_fetch_benchmark_composition_window_maps_not_found_to_404() -> None:
    mock_service = MagicMock(spec=IntegrationService)
    mock_service.get_benchmark_composition_window = AsyncMock(return_value=None)

    with pytest.raises(HTTPException) as exc_info:
        await fetch_benchmark_composition_window(
            benchmark_id="BMK_MISSING",
            request=BenchmarkCompositionWindowRequest(
                window=IntegrationWindow(start_date="2026-01-01", end_date="2026-03-31")
            ),
            integration_service=mock_service,
        )

    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_fetch_benchmark_composition_window_maps_currency_conflict_to_409() -> None:
    mock_service = MagicMock(spec=IntegrationService)
    mock_service.get_benchmark_composition_window = AsyncMock(
        side_effect=ValueError(
            "Benchmark definition currency changed within requested composition window."
        )
    )

    with pytest.raises(HTTPException) as exc_info:
        await fetch_benchmark_composition_window(
            benchmark_id="BMK_CONFLICT",
            request=BenchmarkCompositionWindowRequest(
                window=IntegrationWindow(start_date="2026-01-01", end_date="2026-03-31")
            ),
            integration_service=mock_service,
        )

    assert exc_info.value.status_code == 409


@pytest.mark.asyncio
async def test_fetch_benchmark_definition_not_found_maps_404() -> None:
    mock_service = MagicMock(spec=IntegrationService)
    mock_service.get_benchmark_definition = AsyncMock(return_value=None)

    with pytest.raises(HTTPException) as exc_info:
        await fetch_benchmark_definition(
            benchmark_id="BMK_MISSING",
            request=BenchmarkDefinitionRequest(as_of_date="2026-01-31"),
            integration_service=mock_service,
        )

    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_reference_router_success_paths_cover_all_endpoints() -> None:
    mock_service = MagicMock(spec=IntegrationService)
    mock_service.get_benchmark_composition_window = AsyncMock(
        return_value={
            "benchmark_id": "B1",
            "benchmark_currency": "USD",
            "resolved_window": {"start_date": "2026-01-01", "end_date": "2026-01-31"},
            "segments": [],
            "lineage": {"contract_version": "rfc_062_v1"},
        }
    )
    mock_service.get_benchmark_market_series = AsyncMock(
        return_value={
            "benchmark_id": "B1",
            "as_of_date": "2026-01-31",
            "benchmark_currency": "USD",
            "target_currency": "USD",
            "resolved_window": {"start_date": "2026-01-01", "end_date": "2026-01-31"},
            "frequency": "daily",
            "component_series": [],
            "quality_status_summary": {},
            "fx_context_source_currency": "USD",
            "fx_context_target_currency": "USD",
            "normalization_policy": "native_component_series_downstream_normalization_required",
            "normalization_status": (
                "native_component_series_with_identity_benchmark_to_target_fx_context"
            ),
            "request_fingerprint": "fp1",
            "page": {"page_size": 250, "sort_key": "index_id:asc", "next_page_token": None},
            "lineage": {"contract_version": "rfc_062_v1"},
        }
    )
    mock_service.get_index_price_series = AsyncMock(
        return_value={
            "index_id": "IDX1",
            "resolved_window": {"start_date": "2026-01-01", "end_date": "2026-01-31"},
            "frequency": "daily",
            "points": [],
            "lineage": {"contract_version": "rfc_062_v1"},
        }
    )
    mock_service.get_index_return_series = AsyncMock(
        return_value={
            "index_id": "IDX1",
            "resolved_window": {"start_date": "2026-01-01", "end_date": "2026-01-31"},
            "frequency": "daily",
            "points": [],
            "lineage": {"contract_version": "rfc_062_v1"},
        }
    )
    mock_service.get_benchmark_return_series = AsyncMock(
        return_value={
            "benchmark_id": "B1",
            "resolved_window": {"start_date": "2026-01-01", "end_date": "2026-01-31"},
            "frequency": "daily",
            "points": [],
            "lineage": {"contract_version": "rfc_062_v1"},
        }
    )
    mock_service.get_risk_free_series = AsyncMock(
        return_value={
            "currency": "USD",
            "series_mode": "annualized_rate_series",
            "resolved_window": {"start_date": "2026-01-01", "end_date": "2026-01-31"},
            "frequency": "daily",
            "points": [],
            "lineage": {"contract_version": "rfc_062_v1"},
        }
    )
    mock_service.get_classification_taxonomy = AsyncMock(
        return_value={"as_of_date": "2026-01-31", "records": [], "taxonomy_version": "rfc_062_v1"}
    )
    mock_service.get_risk_free_coverage = AsyncMock(
        return_value={
            "observed_start_date": None,
            "observed_end_date": None,
            "expected_start_date": "2026-01-01",
            "expected_end_date": "2026-01-31",
            "total_points": 0,
            "missing_dates_count": 31,
            "missing_dates_sample": [],
            "quality_status_distribution": {},
        }
    )

    request_window = IntegrationWindow(start_date="2026-01-01", end_date="2026-01-31")
    benchmark_market_response = await fetch_benchmark_market_series(
        benchmark_id="B1",
        request=BenchmarkMarketSeriesRequest(
            as_of_date="2026-01-31",
            window=request_window,
            frequency="daily",
            target_currency="USD",
            series_fields=["index_price"],
        ),
        integration_service=mock_service,
    )
    assert benchmark_market_response["benchmark_id"] == "B1"
    assert benchmark_market_response["benchmark_currency"] == "USD"
    assert benchmark_market_response["page"]["page_size"] == 250
    mock_service.get_benchmark_market_series.assert_awaited_once()

    benchmark_composition_response = await fetch_benchmark_composition_window(
        benchmark_id="B1",
        request=BenchmarkCompositionWindowRequest(window=request_window),
        integration_service=mock_service,
    )
    assert benchmark_composition_response["benchmark_currency"] == "USD"
    mock_service.get_benchmark_composition_window.assert_awaited_once()

    index_price_response = await fetch_index_price_series(
        index_id="IDX1",
        request=IndexSeriesRequest(
            as_of_date="2026-01-31", window=request_window, frequency="daily"
        ),
        integration_service=mock_service,
    )
    assert index_price_response["index_id"] == "IDX1"
    mock_service.get_index_price_series.assert_awaited_once_with(
        index_id="IDX1",
        request=IndexSeriesRequest(
            as_of_date="2026-01-31", window=request_window, frequency="daily"
        ),
    )

    index_return_response = await fetch_index_return_series(
        index_id="IDX1",
        request=IndexSeriesRequest(
            as_of_date="2026-01-31", window=request_window, frequency="daily"
        ),
        integration_service=mock_service,
    )
    assert index_return_response["index_id"] == "IDX1"
    mock_service.get_index_return_series.assert_awaited_once_with(
        index_id="IDX1",
        request=IndexSeriesRequest(
            as_of_date="2026-01-31", window=request_window, frequency="daily"
        ),
    )

    benchmark_return_response = await fetch_benchmark_return_series(
        benchmark_id="B1",
        request=BenchmarkReturnSeriesRequest(
            as_of_date="2026-01-31",
            window=request_window,
            frequency="daily",
        ),
        integration_service=mock_service,
    )
    assert benchmark_return_response["benchmark_id"] == "B1"
    mock_service.get_benchmark_return_series.assert_awaited_once()

    risk_free_response = await fetch_risk_free_series(
        request=RiskFreeSeriesRequest(
            as_of_date="2026-01-31",
            window=request_window,
            frequency="daily",
            currency="USD",
            series_mode="annualized_rate_series",
        ),
        integration_service=mock_service,
    )
    assert risk_free_response["currency"] == "USD"
    mock_service.get_risk_free_series.assert_awaited_once()

    taxonomy_response = await fetch_classification_taxonomy(
        request=ClassificationTaxonomyRequest(as_of_date="2026-01-31"),
        integration_service=mock_service,
    )
    assert taxonomy_response["taxonomy_version"] == "rfc_062_v1"
    mock_service.get_classification_taxonomy.assert_awaited_once_with(
        as_of_date=ClassificationTaxonomyRequest(as_of_date="2026-01-31").as_of_date,
        taxonomy_scope=None,
    )

    risk_free_coverage_response = await get_risk_free_coverage(
        currency="USD",
        request=CoverageRequest(window=request_window),
        integration_service=mock_service,
    )
    assert risk_free_coverage_response["total_points"] == 0
    mock_service.get_risk_free_coverage.assert_awaited_once_with(
        currency="USD",
        start_date=request_window.start_date,
        end_date=request_window.end_date,
    )


@pytest.mark.asyncio
async def test_fetch_benchmark_market_series_maps_invalid_page_token_to_400() -> None:
    mock_service = MagicMock(spec=IntegrationService)
    mock_service.get_benchmark_market_series = AsyncMock(
        side_effect=ValueError("Malformed page token.")
    )

    with pytest.raises(HTTPException) as exc_info:
        await fetch_benchmark_market_series(
            benchmark_id="B1",
            request=BenchmarkMarketSeriesRequest(
                as_of_date="2026-01-31",
                window=IntegrationWindow(start_date="2026-01-01", end_date="2026-01-31"),
                frequency="daily",
                target_currency="USD",
                series_fields=["index_price"],
            ),
            integration_service=mock_service,
        )

    assert exc_info.value.status_code == 400
