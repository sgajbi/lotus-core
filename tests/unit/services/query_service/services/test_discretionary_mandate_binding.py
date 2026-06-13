import asyncio
from datetime import UTC, date, datetime
from decimal import Decimal
from types import SimpleNamespace

from src.services.query_service.app.dtos.reference_integration_dto import (
    DiscretionaryMandateBindingRequest,
)
from src.services.query_service.app.services.discretionary_mandate_binding import (
    build_discretionary_mandate_binding_response,
    resolve_discretionary_mandate_binding_response,
)


def _request(
    *,
    as_of_date: date = date(2026, 4, 10),
    include_policy_pack: bool = True,
) -> DiscretionaryMandateBindingRequest:
    return DiscretionaryMandateBindingRequest(
        as_of_date=as_of_date,
        include_policy_pack=include_policy_pack,
    )


def _binding_row(**overrides: object) -> SimpleNamespace:
    fields = {
        "portfolio_id": "PB_SG_GLOBAL_BAL_001",
        "mandate_id": "MANDATE_PB_SG_GLOBAL_BAL_001",
        "client_id": "CIF_SG_000184",
        "mandate_type": "discretionary",
        "discretionary_authority_status": " active ",
        "booking_center_code": "Singapore",
        "jurisdiction_code": "SG",
        "model_portfolio_id": "MODEL_PB_SG_GLOBAL_BAL_DPM",
        "policy_pack_id": "POLICY_DPM_SG_BALANCED_V1",
        "mandate_objective": (
            "Preserve and grow global balanced wealth within controlled drawdown limits."
        ),
        "risk_profile": "balanced",
        "investment_horizon": "long_term",
        "review_cadence": "quarterly",
        "last_review_date": date(2026, 3, 31),
        "next_review_due_date": date(2026, 6, 30),
        "leverage_allowed": False,
        "tax_awareness_allowed": True,
        "settlement_awareness_required": True,
        "rebalance_frequency": "monthly",
        "rebalance_bands": {
            "default_band": "0.0250000000",
            "cash_reserve_weight": "0.0200000000",
        },
        "effective_from": date(2026, 4, 1),
        "effective_to": None,
        "binding_version": 1,
        "source_system": "mandate_admin",
        "source_record_id": "mandate_001_v1",
        "observed_at": datetime(2026, 4, 1, 9, 0, tzinfo=UTC),
        "quality_status": " accepted ",
    }
    fields.update(overrides)
    return SimpleNamespace(**fields)


def test_build_discretionary_mandate_binding_response_marks_ready() -> None:
    response = build_discretionary_mandate_binding_response(
        row=_binding_row(),
        request=_request(),
    )

    assert response.product_name == "DiscretionaryMandateBinding"
    assert response.policy_pack_id == "POLICY_DPM_SG_BALANCED_V1"
    assert response.discretionary_authority_status == "ACTIVE"
    assert response.rebalance_bands.default_band == Decimal("0.0250000000")
    assert response.rebalance_bands.cash_reserve_weight == Decimal("0.0200000000")
    assert response.supportability.state == "READY"
    assert response.supportability.reason == "MANDATE_BINDING_READY"
    assert response.supportability.missing_data_families == []
    assert response.data_quality_status == "ACCEPTED"
    assert response.latest_evidence_timestamp == datetime(2026, 4, 1, 9, 0, tzinfo=UTC)
    assert response.lineage == {
        "source_system": "mandate_admin",
        "source_record_id": "mandate_001_v1",
        "contract_version": "rfc_087_v1",
    }


def test_resolve_discretionary_mandate_binding_response_orchestrates_repository_read() -> None:
    async def run_case() -> tuple[object, list[dict[str, object]]]:
        calls: list[dict[str, object]] = []

        class Repository:
            async def resolve_discretionary_mandate_binding(
                self,
                **kwargs: object,
            ) -> SimpleNamespace:
                calls.append(kwargs)
                return _binding_row()

        response = await resolve_discretionary_mandate_binding_response(
            repository=Repository(),
            portfolio_id="PB_SG_GLOBAL_BAL_001",
            request=DiscretionaryMandateBindingRequest(
                as_of_date=date(2026, 4, 10),
                mandate_id="MANDATE_PB_SG_GLOBAL_BAL_001",
                booking_center_code="Singapore",
                include_policy_pack=True,
            ),
        )
        return response, calls

    response, calls = asyncio.run(run_case())

    assert response is not None
    assert response.product_name == "DiscretionaryMandateBinding"
    assert response.supportability.state == "READY"
    assert calls == [
        {
            "portfolio_id": "PB_SG_GLOBAL_BAL_001",
            "as_of_date": date(2026, 4, 10),
            "mandate_id": "MANDATE_PB_SG_GLOBAL_BAL_001",
            "booking_center_code": "Singapore",
        }
    ]


def test_resolve_discretionary_mandate_binding_response_returns_none_when_missing() -> None:
    async def run_case() -> tuple[object, list[dict[str, object]]]:
        calls: list[dict[str, object]] = []

        class Repository:
            async def resolve_discretionary_mandate_binding(
                self,
                **kwargs: object,
            ) -> None:
                calls.append(kwargs)
                return None

        response = await resolve_discretionary_mandate_binding_response(
            repository=Repository(),
            portfolio_id="PB_SG_GLOBAL_BAL_001",
            request=DiscretionaryMandateBindingRequest(
                as_of_date=date(2026, 4, 10),
                include_policy_pack=True,
            ),
        )
        return response, calls

    response, calls = asyncio.run(run_case())

    assert response is None
    assert calls == [
        {
            "portfolio_id": "PB_SG_GLOBAL_BAL_001",
            "as_of_date": date(2026, 4, 10),
            "mandate_id": None,
            "booking_center_code": None,
        }
    ]


def test_build_discretionary_mandate_binding_response_hides_policy_pack_when_excluded() -> None:
    response = build_discretionary_mandate_binding_response(
        row=_binding_row(policy_pack_id="POLICY_DPM_SG_BALANCED_V1"),
        request=_request(include_policy_pack=False),
    )

    assert response.policy_pack_id is None
    assert response.supportability.state == "READY"


def test_build_discretionary_mandate_binding_response_blocks_inactive_authority() -> None:
    response = build_discretionary_mandate_binding_response(
        row=_binding_row(discretionary_authority_status="suspended"),
        request=_request(),
    )

    assert response.supportability.state == "INCOMPLETE"
    assert response.supportability.reason == "DISCRETIONARY_AUTHORITY_NOT_ACTIVE"
    assert response.supportability.missing_data_families == ["active_discretionary_authority"]


def test_build_discretionary_mandate_binding_response_flags_missing_policy_pack() -> None:
    response = build_discretionary_mandate_binding_response(
        row=_binding_row(policy_pack_id=None),
        request=_request(include_policy_pack=True),
    )

    assert response.supportability.state == "INCOMPLETE"
    assert response.supportability.reason == "MANDATE_POLICY_PACK_MISSING"
    assert response.supportability.missing_data_families == ["policy_pack"]


def test_build_discretionary_mandate_binding_response_preserves_policy_pack_priority() -> None:
    response = build_discretionary_mandate_binding_response(
        row=_binding_row(discretionary_authority_status="suspended", policy_pack_id=None),
        request=_request(include_policy_pack=True),
    )

    assert response.supportability.state == "INCOMPLETE"
    assert response.supportability.reason == "MANDATE_POLICY_PACK_MISSING"
    assert response.supportability.missing_data_families == [
        "active_discretionary_authority",
        "policy_pack",
    ]


def test_build_discretionary_mandate_binding_response_flags_missing_review_data() -> None:
    response = build_discretionary_mandate_binding_response(
        row=_binding_row(mandate_objective=None, review_cadence=None, next_review_due_date=None),
        request=_request(),
    )

    assert response.supportability.state == "INCOMPLETE"
    assert response.supportability.reason == "MANDATE_OBJECTIVE_MISSING"
    assert response.supportability.missing_data_families == [
        "mandate_objective",
        "mandate_review_schedule",
    ]


def test_build_discretionary_mandate_binding_response_degrades_overdue_review() -> None:
    response = build_discretionary_mandate_binding_response(
        row=_binding_row(next_review_due_date=date(2026, 3, 31)),
        request=_request(as_of_date=date(2026, 4, 10)),
    )

    assert response.supportability.state == "DEGRADED"
    assert response.supportability.reason == "MANDATE_REVIEW_OVERDUE"


def test_build_discretionary_mandate_binding_response_defaults_sparse_bands() -> None:
    response = build_discretionary_mandate_binding_response(
        row=_binding_row(rebalance_bands={"default_band": " ", "cash_reserve_weight": ""}),
        request=_request(),
    )

    assert response.rebalance_bands.default_band == Decimal("0")
    assert response.rebalance_bands.cash_reserve_weight is None
