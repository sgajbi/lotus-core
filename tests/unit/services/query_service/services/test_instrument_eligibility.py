from datetime import date, datetime
from types import SimpleNamespace

from src.services.query_service.app.dtos.reference_integration_dto import (
    InstrumentEligibilityBulkRequest,
)
from src.services.query_service.app.services.instrument_eligibility import (
    build_instrument_eligibility_bulk_response,
)


def _eligibility_row(security_id: str = " EQ_US_AAPL ") -> SimpleNamespace:
    return SimpleNamespace(
        security_id=security_id,
        eligibility_status="APPROVED",
        product_shelf_status="APPROVED",
        buy_allowed=True,
        sell_allowed=True,
        restriction_reason_codes=[],
        settlement_days=2,
        settlement_calendar_id="NYSE",
        liquidity_tier="T1",
        issuer_id="ISSUER_AAPL",
        issuer_name="Apple Inc.",
        ultimate_parent_issuer_id="ISSUER_AAPL",
        ultimate_parent_issuer_name="Apple Inc.",
        asset_class="equity",
        country_of_risk="US",
        effective_from=date(2026, 1, 1),
        effective_to=None,
        quality_status="accepted",
        source_record_id="eligibility:EQ_US_AAPL",
        source_timestamp=datetime(2026, 4, 10, 9, 0, 0),
    )


def test_build_instrument_eligibility_bulk_response_preserves_request_order() -> None:
    response = build_instrument_eligibility_bulk_response(
        request=InstrumentEligibilityBulkRequest(
            security_ids=["UNKNOWN_SEC", "EQ_US_AAPL"],
            as_of_date=date(2026, 4, 10),
        ),
        rows=[_eligibility_row()],
    )

    assert [record.security_id for record in response.records] == [
        "UNKNOWN_SEC",
        "EQ_US_AAPL",
    ]
    assert response.records[0].found is False
    assert response.records[1].found is True
    assert response.supportability.state == "INCOMPLETE"
    assert response.supportability.reason == "INSTRUMENT_ELIGIBILITY_MISSING"
    assert response.supportability.missing_security_ids == ["UNKNOWN_SEC"]
    assert response.data_quality_status == "PARTIAL"
    assert response.latest_evidence_timestamp == datetime(2026, 4, 10, 9, 0, 0)


def test_build_instrument_eligibility_bulk_response_marks_ready_when_complete() -> None:
    response = build_instrument_eligibility_bulk_response(
        request=InstrumentEligibilityBulkRequest(
            security_ids=["EQ_US_AAPL"],
            as_of_date=date(2026, 4, 10),
        ),
        rows=[_eligibility_row()],
    )

    assert response.supportability.state == "READY"
    assert response.supportability.resolved_count == 1
    assert response.data_quality_status == "COMPLETE"
    assert response.lineage == {
        "source_system": "instrument_eligibility",
        "contract_version": "rfc_087_v1",
    }
