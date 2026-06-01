from datetime import UTC, date, datetime
from types import SimpleNamespace

from src.services.query_service.app.dtos.reference_integration_dto import (
    ExternalHedgeExecutionReadinessRequest,
)
from src.services.query_service.app.services.external_hedge_execution_readiness import (
    EXTERNAL_HEDGE_EXECUTION_BLOCKED_CAPABILITIES,
    EXTERNAL_HEDGE_EXECUTION_MISSING_FAMILIES,
    build_external_hedge_execution_readiness_response,
)


def _binding(as_of_date: date = date(2026, 5, 3)) -> SimpleNamespace:
    return SimpleNamespace(
        portfolio_id="PB_SG_GLOBAL_BAL_001",
        mandate_id="MANDATE_PB_SG_GLOBAL_BAL_001",
        client_id="CIF_SG_000184",
        effective_from=as_of_date,
        observed_at=datetime(2026, 5, 3, 8, tzinfo=UTC),
        updated_at=datetime(2026, 5, 3, 8, tzinfo=UTC),
    )


def _request() -> ExternalHedgeExecutionReadinessRequest:
    return ExternalHedgeExecutionReadinessRequest(
        as_of_date=date(2026, 5, 3),
        tenant_id="default",
        mandate_id="MANDATE_PB_SG_GLOBAL_BAL_001",
        reporting_currency="USD",
        exposure_currencies=["JPY", "EUR"],
    )


def test_build_external_hedge_execution_readiness_response_fails_closed() -> None:
    response = build_external_hedge_execution_readiness_response(
        portfolio_id="PB_SG_GLOBAL_BAL_001",
        binding=_binding(),
        request=_request(),
    )

    assert response.product_name == "ExternalHedgeExecutionReadiness"
    assert response.client_id == "CIF_SG_000184"
    assert response.reporting_currency == "USD"
    assert response.exposure_currencies == ["JPY", "EUR"]
    assert response.readiness_checks == []
    assert response.supportability.state == "UNAVAILABLE"
    assert response.supportability.reason == "EXTERNAL_TREASURY_SOURCE_NOT_INGESTED"
    assert response.supportability.missing_data_families == (
        EXTERNAL_HEDGE_EXECUTION_MISSING_FAMILIES
    )
    assert response.supportability.blocked_capabilities == (
        EXTERNAL_HEDGE_EXECUTION_BLOCKED_CAPABILITIES
    )
    assert response.data_quality_status == "MISSING"
    assert response.latest_evidence_timestamp is None
    assert response.source_batch_fingerprint is not None
    assert response.snapshot_id is not None
    assert response.snapshot_id.startswith("external_hedge_execution_readiness:")
    assert response.lineage == {
        "source_system": "external-bank-treasury",
        "source_table": "not_ingested",
        "contract_version": "rfc_039_external_hedge_execution_readiness_v1",
        "integration_status": "not_ingested",
        "runtime_posture": "fail_closed",
        "non_claims": ",".join(EXTERNAL_HEDGE_EXECUTION_BLOCKED_CAPABILITIES),
    }
