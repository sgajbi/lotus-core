from datetime import date
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
    get_portfolio_tax_lot_window,
    get_risk_free_coverage,
    resolve_instrument_eligibility_bulk,
    resolve_discretionary_mandate_binding,
    resolve_model_portfolio_targets,
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
    DiscretionaryMandateBindingRequest,
    IndexCatalogRequest,
    IndexSeriesRequest,
    InstrumentEligibilityBulkRequest,
    IntegrationWindow,
    ModelPortfolioTargetRequest,
    PortfolioTaxLotWindowRequest,
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
            "liquidity_tier": "L1",
        }
    ]

    response = await get_instrument_enrichment_bulk(
        request=InstrumentEnrichmentBulkRequest(security_ids=["SEC_AAPL_US"]),
        service=mock_service,
    )

    assert response.records[0].security_id == "SEC_AAPL_US"
    assert response.records[0].liquidity_tier == "L1"
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
async def test_resolve_model_portfolio_targets_success_path() -> None:
    mock_service = MagicMock(spec=IntegrationService)
    mock_service.resolve_model_portfolio_targets = AsyncMock(
        return_value={
            "product_name": "DpmModelPortfolioTarget",
            "product_version": "v1",
            "model_portfolio_id": "MODEL_SG_BALANCED_DPM",
            "model_portfolio_version": "2026.03",
            "display_name": "Singapore Balanced DPM Model",
            "base_currency": "SGD",
            "risk_profile": "balanced",
            "mandate_type": "discretionary",
            "rebalance_frequency": "monthly",
            "approval_status": "approved",
            "approved_at": None,
            "effective_from": "2026-03-25",
            "effective_to": None,
            "targets": [],
            "supportability": {
                "state": "INCOMPLETE",
                "reason": "MODEL_TARGETS_EMPTY",
                "target_count": 0,
                "total_target_weight": "0",
            },
            "lineage": {
                "source_system": "investment_office_model_system",
                "source_record_id": "model_sg_balanced_202603",
                "contract_version": "rfc_087_v1",
            },
        }
    )
    request = ModelPortfolioTargetRequest(as_of_date="2026-03-31")

    response = await resolve_model_portfolio_targets(
        model_portfolio_id="MODEL_SG_BALANCED_DPM",
        request=request,
        integration_service=mock_service,
    )

    assert response["product_name"] == "DpmModelPortfolioTarget"
    mock_service.resolve_model_portfolio_targets.assert_awaited_once_with(
        model_portfolio_id="MODEL_SG_BALANCED_DPM",
        request=request,
    )


@pytest.mark.asyncio
async def test_resolve_model_portfolio_targets_maps_not_found_to_404() -> None:
    mock_service = MagicMock(spec=IntegrationService)
    mock_service.resolve_model_portfolio_targets = AsyncMock(return_value=None)

    with pytest.raises(HTTPException) as exc_info:
        await resolve_model_portfolio_targets(
            model_portfolio_id="MODEL_MISSING",
            request=ModelPortfolioTargetRequest(as_of_date="2026-03-31"),
            integration_service=mock_service,
        )

    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_resolve_discretionary_mandate_binding_success_path() -> None:
    mock_service = MagicMock(spec=IntegrationService)
    mock_service.resolve_discretionary_mandate_binding = AsyncMock(
        return_value={
            "product_name": "DiscretionaryMandateBinding",
            "product_version": "v1",
            "portfolio_id": "PB_SG_GLOBAL_BAL_001",
            "mandate_id": "MANDATE_PB_SG_GLOBAL_BAL_001",
            "client_id": "CIF_SG_000184",
            "mandate_type": "discretionary",
            "discretionary_authority_status": "active",
            "booking_center_code": "Singapore",
            "jurisdiction_code": "SG",
            "model_portfolio_id": "MODEL_PB_SG_GLOBAL_BAL_DPM",
            "policy_pack_id": "POLICY_DPM_SG_BALANCED_V1",
            "risk_profile": "balanced",
            "investment_horizon": "long_term",
            "leverage_allowed": False,
            "tax_awareness_allowed": True,
            "settlement_awareness_required": True,
            "rebalance_frequency": "monthly",
            "rebalance_bands": {
                "default_band": "0.0250000000",
                "cash_reserve_weight": "0.0200000000",
            },
            "effective_from": "2026-04-01",
            "effective_to": None,
            "binding_version": 1,
            "supportability": {
                "state": "READY",
                "reason": "MANDATE_BINDING_READY",
                "missing_data_families": [],
            },
            "lineage": {"contract_version": "rfc_087_v1"},
        }
    )
    request = DiscretionaryMandateBindingRequest(as_of_date="2026-04-10")

    response = await resolve_discretionary_mandate_binding(
        portfolio_id="PB_SG_GLOBAL_BAL_001",
        request=request,
        integration_service=mock_service,
    )

    assert response["product_name"] == "DiscretionaryMandateBinding"
    assert response["model_portfolio_id"] == "MODEL_PB_SG_GLOBAL_BAL_DPM"
    mock_service.resolve_discretionary_mandate_binding.assert_awaited_once_with(
        portfolio_id="PB_SG_GLOBAL_BAL_001",
        request=request,
    )


@pytest.mark.asyncio
async def test_resolve_discretionary_mandate_binding_maps_not_found_to_404() -> None:
    mock_service = MagicMock(spec=IntegrationService)
    mock_service.resolve_discretionary_mandate_binding = AsyncMock(return_value=None)

    with pytest.raises(HTTPException) as exc_info:
        await resolve_discretionary_mandate_binding(
            portfolio_id="PB_SG_GLOBAL_BAL_001",
            request=DiscretionaryMandateBindingRequest(as_of_date="2026-04-10"),
            integration_service=mock_service,
        )

    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_resolve_instrument_eligibility_bulk_success_path() -> None:
    mock_service = MagicMock(spec=IntegrationService)
    mock_service.resolve_instrument_eligibility_bulk = AsyncMock(
        return_value={
            "product_name": "InstrumentEligibilityProfile",
            "product_version": "v1",
            "as_of_date": "2026-04-10",
            "generated_at": "2026-04-10T09:00:00Z",
            "restatement_version": "current",
            "reconciliation_status": "NOT_ASSESSED",
            "data_quality_status": "COMPLETE",
            "latest_evidence_timestamp": "2026-04-10T09:00:00Z",
            "source_batch_fingerprint": "abc",
            "snapshot_id": "snap",
            "policy_version": "default",
            "correlation_id": None,
            "records": [
                {
                    "security_id": "AAPL",
                    "found": True,
                    "eligibility_status": "APPROVED",
                    "product_shelf_status": "APPROVED",
                    "buy_allowed": True,
                    "sell_allowed": True,
                    "restriction_reason_codes": [],
                    "settlement_days": 2,
                    "settlement_calendar_id": "US_NYSE",
                    "liquidity_tier": "L1",
                    "issuer_id": "APPLE",
                    "issuer_name": "Apple Inc.",
                    "ultimate_parent_issuer_id": "APPLE_PARENT",
                    "ultimate_parent_issuer_name": "Apple Inc.",
                    "asset_class": "Equity",
                    "country_of_risk": "US",
                    "effective_from": "2026-04-01",
                    "effective_to": None,
                    "quality_status": "ACCEPTED",
                    "source_record_id": "AAPL-elig",
                }
            ],
            "supportability": {
                "state": "READY",
                "reason": "INSTRUMENT_ELIGIBILITY_READY",
                "requested_count": 1,
                "resolved_count": 1,
                "missing_security_ids": [],
            },
            "lineage": {"contract_version": "rfc_087_v1"},
        }
    )
    request = InstrumentEligibilityBulkRequest(
        as_of_date="2026-04-10",
        security_ids=["AAPL"],
    )

    response = await resolve_instrument_eligibility_bulk(
        request=request,
        integration_service=mock_service,
    )

    assert response["product_name"] == "InstrumentEligibilityProfile"
    mock_service.resolve_instrument_eligibility_bulk.assert_awaited_once_with(request)


@pytest.mark.asyncio
async def test_get_portfolio_tax_lot_window_success_path() -> None:
    mock_service = MagicMock(spec=IntegrationService)
    mock_service.get_portfolio_tax_lot_window = AsyncMock(
        return_value={
            "product_name": "PortfolioTaxLotWindow",
            "product_version": "v1",
            "portfolio_id": "PB_SG_GLOBAL_BAL_001",
            "as_of_date": "2026-04-10",
            "generated_at": "2026-04-10T09:00:00Z",
            "restatement_version": "current",
            "reconciliation_status": "NOT_ASSESSED",
            "data_quality_status": "COMPLETE",
            "latest_evidence_timestamp": "2026-04-10T09:00:00Z",
            "source_batch_fingerprint": "abc",
            "snapshot_id": "snap",
            "policy_version": "default",
            "correlation_id": None,
            "lots": [
                {
                    "portfolio_id": "PB_SG_GLOBAL_BAL_001",
                    "security_id": "EQ_US_AAPL",
                    "instrument_id": "EQ_US_AAPL",
                    "lot_id": "LOT-TXN-BUY-AAPL-001",
                    "open_quantity": "100.0000000000",
                    "original_quantity": "100.0000000000",
                    "acquisition_date": "2026-03-25",
                    "cost_basis_base": "15005.5000000000",
                    "cost_basis_local": "15005.5000000000",
                    "local_currency": "USD",
                    "tax_lot_status": "OPEN",
                    "source_transaction_id": "TXN-BUY-AAPL-001",
                    "source_lineage": {"source_system": "front_office_portfolio_seed"},
                }
            ],
            "page": {
                "page_size": 250,
                "sort_key": "acquisition_date:asc,lot_id:asc",
                "returned_component_count": 1,
                "request_scope_fingerprint": "fp",
                "next_page_token": None,
            },
            "supportability": {
                "state": "READY",
                "reason": "TAX_LOTS_READY",
                "requested_security_count": 1,
                "returned_lot_count": 1,
                "missing_security_ids": [],
            },
            "lineage": {"contract_version": "rfc_087_v1"},
        }
    )
    request = PortfolioTaxLotWindowRequest(
        as_of_date="2026-04-10",
        security_ids=["EQ_US_AAPL"],
    )

    response = await get_portfolio_tax_lot_window(
        portfolio_id="PB_SG_GLOBAL_BAL_001",
        request=request,
        integration_service=mock_service,
    )

    assert response["product_name"] == "PortfolioTaxLotWindow"
    mock_service.get_portfolio_tax_lot_window.assert_awaited_once_with(
        portfolio_id="PB_SG_GLOBAL_BAL_001",
        request=request,
    )


@pytest.mark.asyncio
async def test_get_portfolio_tax_lot_window_maps_not_found_to_404() -> None:
    mock_service = MagicMock(spec=IntegrationService)
    mock_service.get_portfolio_tax_lot_window = AsyncMock(side_effect=LookupError("missing"))

    with pytest.raises(HTTPException) as exc_info:
        await get_portfolio_tax_lot_window(
            portfolio_id="P404",
            request=PortfolioTaxLotWindowRequest(as_of_date="2026-04-10"),
            integration_service=mock_service,
        )

    assert exc_info.value.status_code == 404


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
        request=IndexCatalogRequest(
            as_of_date="2026-01-31",
            index_ids=["IDX_MSCI_WORLD_TR"],
        ),
        integration_service=mock_service,
    )

    assert benchmark_response["records"] == []
    assert index_response["records"] == []
    mock_service.list_index_catalog.assert_awaited_once_with(
        as_of_date=date(2026, 1, 31),
        index_ids=["IDX_MSCI_WORLD_TR"],
        index_currency=None,
        index_type=None,
        index_status=None,
    )


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
            "request_fingerprint": "fp-coverage-1",
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
    assert coverage_response["request_fingerprint"] == "fp-coverage-1"


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
            "page": {
                "page_size": 250,
                "sort_key": "index_id:asc",
                "returned_component_count": 0,
                "request_scope_fingerprint": "fp1",
                "next_page_token": None,
            },
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
            "as_of_date": "2026-01-31",
            "resolved_window": {"start_date": "2026-01-01", "end_date": "2026-01-31"},
            "frequency": "daily",
            "request_fingerprint": "fp-index-return-1",
            "points": [],
            "lineage": {"contract_version": "rfc_062_v1"},
        }
    )
    mock_service.get_benchmark_return_series = AsyncMock(
        return_value={
            "benchmark_id": "B1",
            "as_of_date": "2026-01-31",
            "resolved_window": {"start_date": "2026-01-01", "end_date": "2026-01-31"},
            "frequency": "daily",
            "request_fingerprint": "fp-benchmark-return-1",
            "points": [],
            "lineage": {"contract_version": "rfc_062_v1"},
        }
    )
    mock_service.get_risk_free_series = AsyncMock(
        return_value={
            "currency": "USD",
            "as_of_date": "2026-01-31",
            "series_mode": "annualized_rate_series",
            "resolved_window": {"start_date": "2026-01-01", "end_date": "2026-01-31"},
            "frequency": "daily",
            "request_fingerprint": "fp-risk-free-1",
            "points": [],
            "lineage": {"contract_version": "rfc_062_v1"},
        }
    )
    mock_service.get_classification_taxonomy = AsyncMock(
        return_value={
            "as_of_date": "2026-01-31",
            "records": [],
            "taxonomy_version": "rfc_062_v1",
            "request_fingerprint": "fp-taxonomy-1",
        }
    )
    mock_service.get_risk_free_coverage = AsyncMock(
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
    assert benchmark_market_response["page"]["returned_component_count"] == 0
    assert benchmark_market_response["page"]["request_scope_fingerprint"] == "fp1"
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
    assert index_return_response["request_fingerprint"] == "fp-index-return-1"
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
    assert benchmark_return_response["request_fingerprint"] == "fp-benchmark-return-1"
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
    assert risk_free_response["request_fingerprint"] == "fp-risk-free-1"
    mock_service.get_risk_free_series.assert_awaited_once()

    taxonomy_response = await fetch_classification_taxonomy(
        request=ClassificationTaxonomyRequest(as_of_date="2026-01-31"),
        integration_service=mock_service,
    )
    assert taxonomy_response["taxonomy_version"] == "rfc_062_v1"
    assert taxonomy_response["request_fingerprint"] == "fp-taxonomy-1"
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
    assert risk_free_coverage_response["request_fingerprint"] == "fp-risk-free-coverage-1"
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
