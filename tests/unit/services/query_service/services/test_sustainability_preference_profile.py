import asyncio
from datetime import UTC, date, datetime
from decimal import Decimal
from types import SimpleNamespace

from src.services.query_service.app.dtos.reference_integration_dto import (
    SustainabilityPreferenceProfileRequest,
)
from src.services.query_service.app.services.sustainability_preference_profile import (
    build_sustainability_preference_profile_response,
    resolve_sustainability_preference_profile_response,
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


def _preference_row() -> SimpleNamespace:
    return SimpleNamespace(
        preference_framework="LOTUS_SUSTAINABILITY_V1",
        preference_code="MIN_SUSTAINABLE_ALLOCATION",
        preference_status="active",
        preference_source="client_mandate",
        minimum_allocation=Decimal("0.2000000000"),
        maximum_allocation=None,
        applies_to_asset_classes=["equity", "fixed_income"],
        exclusion_codes=["THERMAL_COAL"],
        positive_tilt_codes=["LOW_CARBON_TRANSITION"],
        effective_from=date(2026, 1, 1),
        effective_to=None,
        preference_version=1,
        source_record_id="sustainability:1",
        observed_at=datetime(2026, 5, 3, 9, tzinfo=UTC),
        updated_at=datetime(2026, 5, 3, 9, tzinfo=UTC),
    )


def _request() -> SustainabilityPreferenceProfileRequest:
    return SustainabilityPreferenceProfileRequest(
        as_of_date=date(2026, 5, 3),
        tenant_id="default",
        mandate_id="MANDATE_PB_SG_GLOBAL_BAL_001",
    )


def test_build_sustainability_preference_profile_response_marks_ready() -> None:
    response = build_sustainability_preference_profile_response(
        portfolio_id="PB_SG_GLOBAL_BAL_001",
        binding=_binding(),
        request=_request(),
        rows=[_preference_row()],
    )

    assert response.product_name == "SustainabilityPreferenceProfile"
    assert response.client_id == "CIF_SG_000184"
    assert response.supportability.state == "READY"
    assert response.supportability.reason == "SUSTAINABILITY_PREFERENCE_PROFILE_READY"
    assert response.supportability.preference_count == 1
    assert response.supportability.missing_data_families == []
    assert response.preferences[0].minimum_allocation == Decimal("0.2000000000")
    assert response.preferences[0].exclusion_codes == ["THERMAL_COAL"]
    assert response.data_quality_status == "ACCEPTED"
    assert response.latest_evidence_timestamp == datetime(2026, 5, 3, 9, tzinfo=UTC)
    assert response.source_batch_fingerprint is not None
    assert response.snapshot_id is not None
    assert response.snapshot_id.startswith("sustainability_preference_profile:")
    assert response.lineage == {
        "source_system": "lotus-core-query-service",
        "source_table": "sustainability_preference_profiles,portfolio_mandate_bindings",
        "contract_version": "rfc_040_sustainability_preference_profile_v1",
    }


def test_resolve_sustainability_preference_profile_response_orchestrates_repository_reads() -> None:
    async def run_case() -> tuple[object, list[tuple[str, dict[str, object]]]]:
        calls: list[tuple[str, dict[str, object]]] = []

        class Repository:
            async def resolve_discretionary_mandate_binding(
                self, **kwargs: object
            ) -> SimpleNamespace:
                calls.append(("binding", kwargs))
                return _binding()

            async def list_sustainability_preference_profiles(
                self, **kwargs: object
            ) -> list[SimpleNamespace]:
                calls.append(("preferences", kwargs))
                return [_preference_row()]

        response = await resolve_sustainability_preference_profile_response(
            repository=Repository(),
            portfolio_id="PB_SG_GLOBAL_BAL_001",
            request=_request(),
        )
        return response, calls

    response, calls = asyncio.run(run_case())

    assert response is not None
    assert response.client_id == "CIF_SG_000184"
    assert response.supportability.state == "READY"
    assert calls == [
        (
            "binding",
            {
                "portfolio_id": "PB_SG_GLOBAL_BAL_001",
                "as_of_date": date(2026, 5, 3),
                "mandate_id": "MANDATE_PB_SG_GLOBAL_BAL_001",
            },
        ),
        (
            "preferences",
            {
                "portfolio_id": "PB_SG_GLOBAL_BAL_001",
                "client_id": "CIF_SG_000184",
                "as_of_date": date(2026, 5, 3),
                "mandate_id": "MANDATE_PB_SG_GLOBAL_BAL_001",
                "include_inactive_preferences": False,
            },
        ),
    ]


def test_resolve_sustainability_preference_profile_response_skips_rows_without_binding() -> None:
    async def run_case() -> tuple[object | None, list[str]]:
        calls: list[str] = []

        class Repository:
            async def resolve_discretionary_mandate_binding(self, **_: object) -> None:
                calls.append("binding")
                return None

            async def list_sustainability_preference_profiles(self, **_: object) -> list[object]:
                calls.append("preferences")
                raise AssertionError("Unexpected preference read without mandate binding")

        response = await resolve_sustainability_preference_profile_response(
            repository=Repository(),
            portfolio_id="PB_SG_GLOBAL_BAL_001",
            request=_request(),
        )
        return response, calls

    response, calls = asyncio.run(run_case())

    assert response is None
    assert calls == ["binding"]


def test_build_sustainability_preference_profile_response_marks_empty_missing() -> None:
    response = build_sustainability_preference_profile_response(
        portfolio_id="PB_SG_GLOBAL_BAL_001",
        binding=_binding(),
        request=_request(),
        rows=[],
    )

    assert response.preferences == []
    assert response.supportability.state == "INCOMPLETE"
    assert response.supportability.reason == "SUSTAINABILITY_PREFERENCE_PROFILE_EMPTY"
    assert response.supportability.preference_count == 0
    assert response.supportability.missing_data_families == ["sustainability_preferences"]
    assert response.data_quality_status == "MISSING"
    assert response.latest_evidence_timestamp == datetime(2026, 5, 3, 8, tzinfo=UTC)
