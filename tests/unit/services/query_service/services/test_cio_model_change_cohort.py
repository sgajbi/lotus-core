import asyncio
from datetime import UTC, date, datetime
from types import SimpleNamespace

from src.services.query_service.app.dtos.reference_integration_dto import (
    CioModelChangeAffectedCohortRequest,
)
from src.services.query_service.app.services.cio_model_change_cohort import (
    build_cio_model_change_affected_cohort_response,
    resolve_cio_model_change_affected_cohort_response,
)


def _request(
    *,
    include_inactive_mandates: bool = False,
) -> CioModelChangeAffectedCohortRequest:
    return CioModelChangeAffectedCohortRequest(
        as_of_date=date(2026, 5, 3),
        tenant_id="default",
        booking_center_code="Singapore",
        include_inactive_mandates=include_inactive_mandates,
    )


def _definition(
    *,
    source_system: str | None = "cio_model_admin",
    source_record_id: str | None = "model-def-2026-05",
) -> SimpleNamespace:
    return SimpleNamespace(
        model_portfolio_id="MODEL_PB_SG_GLOBAL_BAL_DPM",
        model_portfolio_version="2026.05",
        approval_status="approved",
        approved_at=datetime(2026, 5, 1, 8, 0, tzinfo=UTC),
        effective_from=date(2026, 5, 1),
        effective_to=None,
        source_system=source_system,
        source_record_id=source_record_id,
        observed_at=datetime(2026, 5, 1, 8, 1, tzinfo=UTC),
        updated_at=datetime(2026, 5, 1, 8, 2, tzinfo=UTC),
    )


def _mandate_row() -> SimpleNamespace:
    return SimpleNamespace(
        portfolio_id="PB_SG_GLOBAL_BAL_001",
        mandate_id="MANDATE_PB_SG_GLOBAL_BAL_001",
        client_id="CIF_SG_000184",
        booking_center_code="Singapore",
        jurisdiction_code="SG",
        discretionary_authority_status="active",
        model_portfolio_id="MODEL_PB_SG_GLOBAL_BAL_DPM",
        policy_pack_id="POLICY_DPM_SG_BALANCED_V1",
        risk_profile="balanced",
        effective_from=date(2026, 5, 1),
        effective_to=None,
        binding_version=3,
        source_record_id="mandate-binding-001",
        observed_at=datetime(2026, 5, 1, 8, 3, tzinfo=UTC),
        updated_at=datetime(2026, 5, 1, 8, 4, tzinfo=UTC),
    )


def test_build_cio_model_change_affected_cohort_response_marks_ready() -> None:
    response = build_cio_model_change_affected_cohort_response(
        definition=_definition(),
        request=_request(),
        mandate_rows=[_mandate_row()],
    )

    assert response.product_name == "CioModelChangeAffectedCohort"
    assert response.model_portfolio_id == "MODEL_PB_SG_GLOBAL_BAL_DPM"
    assert response.model_change_event_id.startswith(
        "cio_model_change:MODEL_PB_SG_GLOBAL_BAL_DPM:2026.05:2026-05-03:"
    )
    assert response.affected_mandates[0].portfolio_id == "PB_SG_GLOBAL_BAL_001"
    assert response.affected_mandates[0].binding_version == 3
    assert response.supportability.state == "READY"
    assert response.supportability.reason == "CIO_MODEL_CHANGE_COHORT_READY"
    assert response.supportability.returned_mandate_count == 1
    assert response.supportability.filters_applied == [
        "model_portfolio_id",
        "as_of_date",
        "booking_center_code",
        "active_discretionary_authority",
    ]
    assert response.data_quality_status == "ACCEPTED"
    assert response.latest_evidence_timestamp == datetime(2026, 5, 1, 8, 4, tzinfo=UTC)
    assert response.source_batch_fingerprint is None
    assert response.snapshot_id is not None
    assert response.snapshot_id.startswith("cio_model_change_cohort:")
    assert response.lineage == {
        "source_system": "cio_model_admin",
        "model_definition_source_record_id": "model-def-2026-05",
        "mandate_binding_table": "portfolio_mandate_bindings",
        "contract_version": "rfc_041_cio_model_change_cohort_v1",
    }


def test_resolve_cio_model_change_affected_cohort_response_orchestrates_repository_reads() -> None:
    async def run_case() -> tuple[object, list[tuple[str, dict[str, object]]]]:
        calls: list[tuple[str, dict[str, object]]] = []

        class Repository:
            async def resolve_model_portfolio_definition(self, **kwargs: object) -> SimpleNamespace:
                calls.append(("definition", kwargs))
                return _definition()

            async def list_model_portfolio_affected_mandates(
                self, **kwargs: object
            ) -> list[SimpleNamespace]:
                calls.append(("mandates", kwargs))
                return [_mandate_row()]

        response = await resolve_cio_model_change_affected_cohort_response(
            repository=Repository(),
            model_portfolio_id="MODEL_PB_SG_GLOBAL_BAL_DPM",
            request=_request(),
        )
        return response, calls

    response, calls = asyncio.run(run_case())

    assert response is not None
    assert response.supportability.state == "READY"
    assert response.affected_mandates[0].portfolio_id == "PB_SG_GLOBAL_BAL_001"
    assert calls == [
        (
            "definition",
            {
                "model_portfolio_id": "MODEL_PB_SG_GLOBAL_BAL_DPM",
                "as_of_date": date(2026, 5, 3),
            },
        ),
        (
            "mandates",
            {
                "model_portfolio_id": "MODEL_PB_SG_GLOBAL_BAL_DPM",
                "as_of_date": date(2026, 5, 3),
                "booking_center_code": "Singapore",
                "include_inactive_mandates": False,
            },
        ),
    ]


def test_resolve_cio_model_change_affected_cohort_response_skips_rows_without_definition() -> None:
    async def run_case() -> tuple[object | None, list[str]]:
        calls: list[str] = []

        class Repository:
            async def resolve_model_portfolio_definition(self, **_: object) -> None:
                calls.append("definition")
                return None

            async def list_model_portfolio_affected_mandates(self, **_: object) -> list[object]:
                calls.append("mandates")
                raise AssertionError("Unexpected mandate read without model definition")

        response = await resolve_cio_model_change_affected_cohort_response(
            repository=Repository(),
            model_portfolio_id="MODEL_MISSING",
            request=_request(),
        )
        return response, calls

    response, calls = asyncio.run(run_case())

    assert response is None
    assert calls == ["definition"]


def test_build_cio_model_change_affected_cohort_response_marks_empty_missing() -> None:
    response = build_cio_model_change_affected_cohort_response(
        definition=_definition(source_system=None, source_record_id=None),
        request=_request(include_inactive_mandates=True),
        mandate_rows=[],
    )

    assert response.affected_mandates == []
    assert response.supportability.state == "INCOMPLETE"
    assert response.supportability.reason == "CIO_MODEL_CHANGE_COHORT_EMPTY"
    assert response.supportability.returned_mandate_count == 0
    assert response.supportability.filters_applied == [
        "model_portfolio_id",
        "as_of_date",
        "booking_center_code",
    ]
    assert response.data_quality_status == "MISSING"
    assert response.lineage["source_system"] == "lotus-core"
    assert response.lineage["model_definition_source_record_id"] == "unknown"
