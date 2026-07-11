"""Application policy tests for bulk instrument eligibility evidence."""

from dataclasses import replace
from datetime import UTC, date, datetime

from src.services.query_control_plane_service.app.application.dpm_source_readiness import (
    instrument_eligibility,
)
from src.services.query_control_plane_service.app.contracts.instrument_eligibility import (
    InstrumentEligibilityBulkRequest,
)
from src.services.query_control_plane_service.app.domain.dpm_source_readiness import (
    InstrumentEligibilityEvidence,
)

GENERATED_AT = datetime(2026, 4, 10, 12, tzinfo=UTC)
EVIDENCE_AT = datetime(2026, 4, 10, 10, tzinfo=UTC)


def _evidence(security_id: str = "EQ_US_AAPL") -> InstrumentEligibilityEvidence:
    return InstrumentEligibilityEvidence(
        security_id=security_id,
        eligibility_status="approved",
        product_shelf_status="approved",
        buy_allowed=True,
        sell_allowed=True,
        restriction_reason_codes=(),
        settlement_days=2,
        settlement_calendar_id="NYSE",
        liquidity_tier="T1",
        issuer_id="APPLE",
        issuer_name="Apple Inc.",
        ultimate_parent_issuer_id="APPLE",
        ultimate_parent_issuer_name="Apple Inc.",
        asset_class="equity",
        country_of_risk="US",
        effective_from=date(2026, 1, 1),
        effective_to=None,
        eligibility_version=1,
        source_system="eligibility_master",
        source_record_id=f"eligibility:{security_id}",
        observed_at=EVIDENCE_AT,
        quality_status="accepted",
        created_at=EVIDENCE_AT,
        updated_at=EVIDENCE_AT,
    )


def _request(*security_ids: str) -> InstrumentEligibilityBulkRequest:
    return InstrumentEligibilityBulkRequest(
        security_ids=list(security_ids),
        as_of_date=date(2026, 4, 10),
        tenant_id="tenant-1",
    )


def test_complete_eligibility_batch_is_ready_current_and_deterministic() -> None:
    request = _request("EQ_US_AAPL")

    first = instrument_eligibility.build_instrument_eligibility_response(
        request=request,
        evidence=[_evidence()],
        generated_at=GENERATED_AT,
    )
    second = instrument_eligibility.build_instrument_eligibility_response(
        request=request,
        evidence=[_evidence()],
        generated_at=datetime(2026, 4, 10, 13, tzinfo=UTC),
    )

    assert first.supportability.state == "READY"
    assert first.data_quality_status == "COMPLETE"
    assert first.source_evidence_current is True
    assert first.freshness_status == "CURRENT"
    assert first.content_hash == second.content_hash
    assert first.source_batch_fingerprint == first.content_hash == first.source_digest


def test_response_preserves_request_order_and_represents_missing_security() -> None:
    response = instrument_eligibility.build_instrument_eligibility_response(
        request=_request("UNKNOWN", "EQ_US_AAPL"),
        evidence=[_evidence()],
        generated_at=GENERATED_AT,
    )

    assert [record.security_id for record in response.records] == ["UNKNOWN", "EQ_US_AAPL"]
    assert response.records[0].found is False
    assert response.records[0].restriction_reason_codes == ["ELIGIBILITY_PROFILE_MISSING"]
    assert response.supportability.state == "INCOMPLETE"
    assert response.supportability.missing_security_ids == ["UNKNOWN"]
    assert response.data_quality_status == "PARTIAL"


def test_unknown_source_status_is_bounded_to_contract_vocabulary() -> None:
    evidence = replace(_evidence(), eligibility_status="new-unmapped-status")

    response = instrument_eligibility.build_instrument_eligibility_response(
        request=_request("EQ_US_AAPL"),
        evidence=[evidence],
        generated_at=GENERATED_AT,
    )

    assert response.records[0].eligibility_status == "UNKNOWN"
