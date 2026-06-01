import asyncio
from datetime import UTC, date, datetime
from types import SimpleNamespace

from src.services.query_service.app.dtos.reference_integration_dto import (
    ClientRestrictionProfileRequest,
)
from src.services.query_service.app.services.client_restriction_profile import (
    build_client_restriction_profile_response,
    resolve_client_restriction_profile_response,
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


def test_resolve_client_restriction_profile_response_orchestrates_repository_reads() -> None:
    async def run_case() -> tuple[object, list[tuple[str, dict[str, object]]]]:
        calls: list[tuple[str, dict[str, object]]] = []

        class Repository:
            async def resolve_discretionary_mandate_binding(
                self, **kwargs: object
            ) -> SimpleNamespace:
                calls.append(("binding", kwargs))
                return _binding()

            async def list_client_restriction_profiles(
                self, **kwargs: object
            ) -> list[SimpleNamespace]:
                calls.append(("restrictions", kwargs))
                return [_restriction_row()]

        response = await resolve_client_restriction_profile_response(
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
            "restrictions",
            {
                "portfolio_id": "PB_SG_GLOBAL_BAL_001",
                "client_id": "CIF_SG_000184",
                "as_of_date": date(2026, 5, 3),
                "mandate_id": "MANDATE_PB_SG_GLOBAL_BAL_001",
                "include_inactive_restrictions": False,
            },
        ),
    ]


def test_resolve_client_restriction_profile_response_skips_rows_without_binding() -> None:
    async def run_case() -> tuple[object | None, list[str]]:
        calls: list[str] = []

        class Repository:
            async def resolve_discretionary_mandate_binding(self, **_: object) -> None:
                calls.append("binding")
                return None

            async def list_client_restriction_profiles(self, **_: object) -> list[object]:
                calls.append("restrictions")
                raise AssertionError("Unexpected restriction read without mandate binding")

        response = await resolve_client_restriction_profile_response(
            repository=Repository(),
            portfolio_id="PB_SG_GLOBAL_BAL_001",
            request=_request(),
        )
        return response, calls

    response, calls = asyncio.run(run_case())

    assert response is None
    assert calls == ["binding"]


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
