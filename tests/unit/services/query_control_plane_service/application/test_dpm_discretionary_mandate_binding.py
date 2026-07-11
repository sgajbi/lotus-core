"""Application policy tests for discretionary mandate binding evidence."""

from dataclasses import replace
from datetime import UTC, date, datetime

import pytest

from src.services.query_control_plane_service.app.application.dpm_source_readiness import (
    discretionary_mandate_binding,
)
from src.services.query_control_plane_service.app.contracts.discretionary_mandate_binding import (
    DiscretionaryMandateBindingRequest,
)
from src.services.query_control_plane_service.app.domain.dpm_source_readiness import (
    DiscretionaryMandateBindingEvidence,
)

GENERATED_AT = datetime(2026, 4, 10, 12, tzinfo=UTC)
EVIDENCE_AT = datetime(2026, 4, 10, 10, tzinfo=UTC)


def _evidence() -> DiscretionaryMandateBindingEvidence:
    return DiscretionaryMandateBindingEvidence(
        portfolio_id="PB_SG_GLOBAL_BAL_001",
        mandate_id="MANDATE_1",
        client_id="CLIENT_1",
        mandate_type="discretionary",
        discretionary_authority_status=" active ",
        booking_center_code="Singapore",
        jurisdiction_code="SG",
        model_portfolio_id="MODEL_1",
        policy_pack_id="POLICY_1",
        mandate_objective="Preserve and grow wealth within controlled drawdown limits.",
        risk_profile="balanced",
        investment_horizon="long_term",
        review_cadence="quarterly",
        last_review_date=date(2026, 3, 31),
        next_review_due_date=date(2026, 6, 30),
        leverage_allowed=False,
        tax_awareness_allowed=True,
        settlement_awareness_required=True,
        rebalance_frequency="monthly",
        rebalance_bands={
            "default_band": "0.0250000000",
            "cash_reserve_weight": "0.0200000000",
        },
        effective_from=date(2026, 4, 1),
        effective_to=None,
        binding_version=3,
        source_system="mandate_admin",
        source_record_id="mandate:1",
        observed_at=EVIDENCE_AT,
        quality_status=" accepted ",
        created_at=EVIDENCE_AT,
        updated_at=EVIDENCE_AT,
    )


def _request(*, include_policy_pack: bool = True) -> DiscretionaryMandateBindingRequest:
    return DiscretionaryMandateBindingRequest(
        as_of_date=date(2026, 4, 10),
        tenant_id="tenant-1",
        include_policy_pack=include_policy_pack,
    )


def _build(
    evidence: DiscretionaryMandateBindingEvidence,
    *,
    include_policy_pack: bool = True,
):
    return discretionary_mandate_binding.build_discretionary_mandate_binding_response(
        evidence=evidence,
        request=_request(include_policy_pack=include_policy_pack),
        generated_at=GENERATED_AT,
    )


def test_active_complete_mandate_is_ready_and_current() -> None:
    response = _build(_evidence())

    assert response.discretionary_authority_status == "ACTIVE"
    assert response.supportability.state == "READY"
    assert response.data_quality_status == "COMPLETE"
    assert response.source_evidence_current is True
    assert response.freshness_status == "CURRENT"
    assert response.source_batch_fingerprint == response.content_hash == response.source_digest
    assert response.rebalance_bands.default_band.as_tuple().exponent == -10
    assert response.source_lineage["source_owner"] == "lotus-core"


def test_policy_pack_can_be_excluded_without_degrading_supportability() -> None:
    response = _build(_evidence(), include_policy_pack=False)

    assert response.policy_pack_id is None
    assert response.supportability.state == "READY"


def test_inactive_authority_and_missing_policy_pack_are_both_reported() -> None:
    response = _build(
        replace(
            _evidence(),
            discretionary_authority_status="suspended",
            policy_pack_id=None,
        )
    )

    assert response.supportability.state == "INCOMPLETE"
    assert response.supportability.reason == "MANDATE_POLICY_PACK_MISSING"
    assert response.supportability.missing_data_families == [
        "active_discretionary_authority",
        "policy_pack",
    ]


def test_missing_objective_and_review_schedule_are_both_reported() -> None:
    response = _build(
        replace(
            _evidence(),
            mandate_objective=None,
            review_cadence=None,
            next_review_due_date=None,
        )
    )

    assert response.supportability.reason == "MANDATE_OBJECTIVE_MISSING"
    assert response.supportability.missing_data_families == [
        "mandate_objective",
        "mandate_review_schedule",
    ]


def test_overdue_review_degrades_otherwise_ready_mandate() -> None:
    response = _build(replace(_evidence(), next_review_due_date=date(2026, 3, 31)))

    assert response.supportability.state == "DEGRADED"
    assert response.supportability.reason == "MANDATE_REVIEW_OVERDUE"


def test_mandate_content_hash_is_independent_of_generation_time() -> None:
    first = _build(_evidence())
    second = discretionary_mandate_binding.build_discretionary_mandate_binding_response(
        evidence=_evidence(),
        request=_request(),
        generated_at=datetime(2026, 4, 10, 13, tzinfo=UTC),
    )

    assert first.generated_at != second.generated_at
    assert first.content_hash == second.content_hash


@pytest.mark.asyncio
async def test_service_resolves_using_all_request_disambiguators() -> None:
    class Reader:
        async def resolve_discretionary_mandate_binding(self, **kwargs: object):
            self.kwargs = kwargs
            return _evidence()

    reader = Reader()
    request = DiscretionaryMandateBindingRequest(
        as_of_date=date(2026, 4, 10),
        mandate_id="MANDATE_1",
        booking_center_code="Singapore",
    )

    response = await discretionary_mandate_binding.DiscretionaryMandateBindingService(
        reader=reader,  # type: ignore[arg-type]
        clock=lambda: GENERATED_AT,
    ).resolve(portfolio_id="PB_SG_GLOBAL_BAL_001", request=request)

    assert response is not None
    assert reader.kwargs == {
        "portfolio_id": "PB_SG_GLOBAL_BAL_001",
        "as_of_date": date(2026, 4, 10),
        "mandate_id": "MANDATE_1",
        "booking_center_code": "Singapore",
    }
