from datetime import UTC, date, datetime
from types import SimpleNamespace

import pytest

from src.services.query_service.app.dtos.reference_integration_dto import (
    DpmPortfolioUniverseCandidateRequest,
)
from src.services.query_service.app.services.dpm_portfolio_universe import (
    build_dpm_portfolio_universe_response,
    dpm_portfolio_universe_after_sort_key,
    dpm_portfolio_universe_next_page_token_payload,
    dpm_portfolio_universe_read_scope,
)


def _request(**kwargs: object) -> DpmPortfolioUniverseCandidateRequest:
    return DpmPortfolioUniverseCandidateRequest(
        as_of_date=date(2026, 5, 3),
        tenant_id="default",
        **kwargs,
    )


def _candidate_row(
    *,
    portfolio_id: str = "PB_SG_GLOBAL_BAL_001",
    mandate_id: str = "MANDATE_PB_SG_GLOBAL_BAL_001",
    updated_at: datetime = datetime(2026, 5, 1, 8, 4, tzinfo=UTC),
) -> SimpleNamespace:
    return SimpleNamespace(
        portfolio_id=portfolio_id,
        mandate_id=mandate_id,
        client_id="CIF_SG_000184",
        booking_center_code="Singapore",
        jurisdiction_code="SG",
        discretionary_authority_status="active",
        model_portfolio_id="MODEL_PB_SG_GLOBAL_BAL_DPM",
        policy_pack_id="POLICY_DPM_SG_BALANCED_V1",
        mandate_objective="global_balanced",
        risk_profile="balanced",
        investment_horizon="medium_term",
        effective_from=date(2026, 5, 1),
        effective_to=None,
        binding_version=3,
        source_record_id="mandate-binding-001",
        observed_at=datetime(2026, 5, 1, 8, 3, tzinfo=UTC),
        updated_at=updated_at,
    )


def test_dpm_portfolio_universe_read_scope_normalizes_filters() -> None:
    read_scope = dpm_portfolio_universe_read_scope(
        _request(
            booking_center_code="  Singapore  ",
            model_portfolio_ids=[" MODEL_B ", "", "MODEL_A", "MODEL_A"],
        )
    )

    assert read_scope.booking_center_code == "Singapore"
    assert read_scope.model_portfolio_ids == ["MODEL_A", "MODEL_B"]
    assert read_scope.request_scope_fingerprint is not None


def test_dpm_portfolio_universe_after_sort_key_rejects_wrong_scope() -> None:
    with pytest.raises(ValueError, match="does not match request scope"):
        dpm_portfolio_universe_after_sort_key(
            cursor={"scope_fingerprint": "wrong-scope"},
            request_scope_fingerprint="expected-scope",
        )


def test_dpm_portfolio_universe_after_sort_key_accepts_scoped_cursor() -> None:
    assert dpm_portfolio_universe_after_sort_key(
        cursor={
            "scope_fingerprint": "expected-scope",
            "last_portfolio_id": "PB_SG_GLOBAL_BAL_001",
            "last_mandate_id": "MANDATE_PB_SG_GLOBAL_BAL_001",
        },
        request_scope_fingerprint="expected-scope",
    ) == ("PB_SG_GLOBAL_BAL_001", "MANDATE_PB_SG_GLOBAL_BAL_001")


def test_build_dpm_portfolio_universe_response_marks_ready() -> None:
    request = _request(booking_center_code="Singapore")
    read_scope = dpm_portfolio_universe_read_scope(request)

    response = build_dpm_portfolio_universe_response(
        request=request,
        read_scope=read_scope,
        page_rows=[_candidate_row()],
        has_more=False,
        next_page_token=None,
    )

    assert response.product_name == "DpmPortfolioUniverseCandidate"
    assert response.supportability.state == "READY"
    assert response.supportability.reason == "DPM_PORTFOLIO_UNIVERSE_READY"
    assert response.supportability.returned_candidate_count == 1
    assert response.supportability.filters_applied == [
        "as_of_date",
        "booking_center_code",
        "active_discretionary_authority",
    ]
    assert response.candidates[0].portfolio_id == "PB_SG_GLOBAL_BAL_001"
    assert response.selection_basis.source_table == "portfolio_mandate_bindings"
    assert "suitability approval" in response.selection_basis.downstream_boundary
    assert response.data_quality_status == "ACCEPTED"
    assert response.latest_evidence_timestamp == datetime(2026, 5, 1, 8, 4, tzinfo=UTC)
    assert response.source_batch_fingerprint == read_scope.request_scope_fingerprint
    assert response.snapshot_id is not None
    assert response.snapshot_id.startswith("dpm_portfolio_universe:")


def test_build_dpm_portfolio_universe_response_marks_partial_page_degraded() -> None:
    request = _request(model_portfolio_ids=["MODEL_PB_SG_GLOBAL_BAL_DPM"])
    read_scope = dpm_portfolio_universe_read_scope(request)
    page_rows = [_candidate_row()]
    token_payload = dpm_portfolio_universe_next_page_token_payload(
        request_scope_fingerprint=read_scope.request_scope_fingerprint,
        page_rows=page_rows,
        has_more=True,
    )

    response = build_dpm_portfolio_universe_response(
        request=request,
        read_scope=read_scope,
        page_rows=page_rows,
        has_more=True,
        next_page_token="encoded-token",
    )

    assert token_payload == {
        "scope_fingerprint": read_scope.request_scope_fingerprint,
        "last_portfolio_id": "PB_SG_GLOBAL_BAL_001",
        "last_mandate_id": "MANDATE_PB_SG_GLOBAL_BAL_001",
    }
    assert response.supportability.state == "DEGRADED"
    assert response.supportability.reason == "DPM_PORTFOLIO_UNIVERSE_PAGE_PARTIAL"
    assert response.supportability.filters_applied == [
        "as_of_date",
        "model_portfolio_ids",
        "active_discretionary_authority",
    ]
    assert response.supportability.page_truncated is True
    assert response.data_quality_status == "PARTIAL"
    assert response.page.next_page_token == "encoded-token"


def test_build_dpm_portfolio_universe_response_marks_empty_missing() -> None:
    request = _request(booking_center_code="   ", include_inactive_mandates=True)
    read_scope = dpm_portfolio_universe_read_scope(request)

    response = build_dpm_portfolio_universe_response(
        request=request,
        read_scope=read_scope,
        page_rows=[],
        has_more=False,
        next_page_token=None,
    )

    assert response.candidates == []
    assert response.supportability.state == "INCOMPLETE"
    assert response.supportability.reason == "DPM_PORTFOLIO_UNIVERSE_EMPTY"
    assert response.supportability.filters_applied == ["as_of_date"]
    assert response.data_quality_status == "MISSING"
