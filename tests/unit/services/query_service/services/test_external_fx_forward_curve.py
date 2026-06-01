from datetime import date

from src.services.query_service.app.dtos.reference_integration_dto import (
    ExternalFXForwardCurveRequest,
)
from src.services.query_service.app.services.external_fx_forward_curve import (
    EXTERNAL_FX_FORWARD_CURVE_BLOCKED_CAPABILITIES,
    EXTERNAL_FX_FORWARD_CURVE_MISSING_FAMILIES,
    build_external_fx_forward_curve_response,
)


def _request() -> ExternalFXForwardCurveRequest:
    return ExternalFXForwardCurveRequest(
        as_of_date=date(2026, 5, 3),
        tenant_id="default",
        reporting_currency="USD",
        currency_pairs=["USD/JPY", "EUR/USD"],
        tenors=["6M", "1M", "3M"],
    )


def test_build_external_fx_forward_curve_response_fails_closed() -> None:
    response = build_external_fx_forward_curve_response(request=_request())

    assert response.product_name == "ExternalFXForwardCurve"
    assert response.reporting_currency == "USD"
    assert response.currency_pairs == ["USD/JPY", "EUR/USD"]
    assert response.tenors == ["6M", "1M", "3M"]
    assert response.curve_points == []
    assert response.supportability.state == "UNAVAILABLE"
    assert response.supportability.reason == "EXTERNAL_TREASURY_SOURCE_NOT_INGESTED"
    assert response.supportability.curve_point_count == 0
    assert response.supportability.missing_data_families == (
        EXTERNAL_FX_FORWARD_CURVE_MISSING_FAMILIES
    )
    assert response.supportability.blocked_capabilities == (
        EXTERNAL_FX_FORWARD_CURVE_BLOCKED_CAPABILITIES
    )
    assert response.data_quality_status == "MISSING"
    assert response.latest_evidence_timestamp is None
    assert response.source_batch_fingerprint is not None
    assert response.snapshot_id is not None
    assert response.snapshot_id.startswith("external_fx_forward_curve:")
    assert response.lineage == {
        "source_system": "external-bank-treasury",
        "source_table": "not_ingested",
        "contract_version": "rfc_039_external_fx_forward_curve_v1",
        "integration_status": "not_ingested",
        "runtime_posture": "fail_closed",
        "non_claims": ",".join(EXTERNAL_FX_FORWARD_CURVE_BLOCKED_CAPABILITIES),
    }
