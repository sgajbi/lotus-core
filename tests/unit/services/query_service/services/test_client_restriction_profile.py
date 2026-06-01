from datetime import UTC, date, datetime
from types import SimpleNamespace

from src.services.query_service.app.dtos.reference_integration_dto import (
    ClientRestrictionProfileRequest,
)
from src.services.query_service.app.services.client_restriction_profile import (
    build_client_restriction_profile_response,
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


def _restriction_row() -> SimpleNamespace:
    return SimpleNamespace(
        restriction_scope="asset_class",
        restriction_code="NO_PRIVATE_CREDIT_BUY",
        restriction_status="active",
        restriction_source="client_mandate",
        applies_to_buy=True,
        applies_to_sell=False,
        instrument_ids=[],
        asset_classes=["private_credit"],
        issuer_ids=[],
        country_codes=[],
        effective_from=date(2026, 1, 1),
        effective_to=None,
        restriction_version=1,
        source_record_id="client-restriction:1",
        observed_at=datetime(2026, 5, 3, 9, tzinfo=UTC),
        updated_at=datetime(2026, 5, 3, 9, tzinfo=UTC),
    )


def _request() -> ClientRestrictionProfileRequest:
    return ClientRestrictionProfileRequest(
        as_of_date=date(2026, 5, 3),
        tenant_id="default",
        mandate_id="MANDATE_PB_SG_GLOBAL_BAL_001",
    )


def test_build_client_restriction_profile_response_marks_ready() -> None:
    response = build_client_restriction_profile_response(
        portfolio_id="PB_SG_GLOBAL_BAL_001",
        binding=_binding(),
        request=_request(),
        rows=[_restriction_row()],
    )

    assert response.product_name == "ClientRestrictionProfile"
    assert response.client_id == "CIF_SG_000184"
    assert response.mandate_id == "MANDATE_PB_SG_GLOBAL_BAL_001"
    assert response.supportability.state == "READY"
    assert response.supportability.reason == "CLIENT_RESTRICTION_PROFILE_READY"
    assert response.supportability.restriction_count == 1
    assert response.supportability.missing_data_families == []
    assert response.restrictions[0].restriction_code == "NO_PRIVATE_CREDIT_BUY"
    assert response.restrictions[0].asset_classes == ["private_credit"]
    assert response.data_quality_status == "ACCEPTED"
    assert response.latest_evidence_timestamp == datetime(2026, 5, 3, 9, tzinfo=UTC)
    assert response.source_batch_fingerprint is not None
    assert response.snapshot_id is not None
    assert response.snapshot_id.startswith("client_restriction_profile:")
    assert response.lineage == {
        "source_system": "lotus-core-query-service",
        "source_table": "client_restriction_profiles,portfolio_mandate_bindings",
        "contract_version": "rfc_040_client_restriction_profile_v1",
    }


def test_build_client_restriction_profile_response_marks_empty_missing() -> None:
    response = build_client_restriction_profile_response(
        portfolio_id="PB_SG_GLOBAL_BAL_001",
        binding=_binding(),
        request=_request(),
        rows=[],
    )

    assert response.restrictions == []
    assert response.supportability.state == "INCOMPLETE"
    assert response.supportability.reason == "CLIENT_RESTRICTION_PROFILE_EMPTY"
    assert response.supportability.restriction_count == 0
    assert response.supportability.missing_data_families == ["client_restrictions"]
    assert response.data_quality_status == "MISSING"
    assert response.latest_evidence_timestamp == datetime(2026, 5, 3, 8, tzinfo=UTC)
