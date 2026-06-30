import asyncio
from datetime import UTC, date, datetime
from decimal import Decimal
from types import SimpleNamespace

from src.services.query_service.app.dtos.reference_integration_dto import (
    ClientTaxProfileRequest,
)
from src.services.query_service.app.services.client_tax_profile import (
    build_client_tax_profile_response,
    resolve_client_tax_profile_response,
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


def _tax_profile_row() -> SimpleNamespace:
    return SimpleNamespace(
        tax_profile_id="TAX_PROFILE_SG_001",
        tax_residency_country="SG",
        booking_tax_jurisdiction="SG",
        tax_status="TAXABLE",
        profile_status="active",
        withholding_tax_rate=Decimal("0.1500000000"),
        capital_gains_tax_applicable=False,
        income_tax_applicable=True,
        treaty_codes=["US_SG_TREATY"],
        eligible_account_types=["DPM"],
        effective_from=date(2026, 1, 1),
        effective_to=None,
        profile_version=1,
        source_record_id="tax-profile:1",
        observed_at=datetime(2026, 5, 3, 9, tzinfo=UTC),
        updated_at=datetime(2026, 5, 3, 9, tzinfo=UTC),
    )


def _request() -> ClientTaxProfileRequest:
    return ClientTaxProfileRequest(
        as_of_date=date(2026, 5, 3),
        tenant_id="default",
        mandate_id="MANDATE_PB_SG_GLOBAL_BAL_001",
    )


def test_build_client_tax_profile_response_marks_ready() -> None:
    response = build_client_tax_profile_response(
        portfolio_id="PB_SG_GLOBAL_BAL_001",
        binding=_binding(),
        request=_request(),
        rows=[_tax_profile_row()],
    )

    assert response.product_name == "ClientTaxProfile"
    assert response.client_id == "CIF_SG_000184"
    assert response.supportability.state == "READY"
    assert response.supportability.reason == "CLIENT_TAX_PROFILE_READY"
    assert response.supportability.profile_count == 1
    assert response.supportability.missing_data_families == []
    assert response.profiles[0].tax_profile_id == "TAX_PROFILE_SG_001"
    assert response.profiles[0].withholding_tax_rate == Decimal("0.1500000000")
    assert response.data_quality_status == "ACCEPTED"
    assert response.latest_evidence_timestamp == datetime(2026, 5, 3, 9, tzinfo=UTC)
    assert response.source_batch_fingerprint is None
    assert response.snapshot_id is not None
    assert response.snapshot_id.startswith("client_tax_profile:")
    assert response.lineage == {
        "source_system": "lotus-core-query-service",
        "source_table": "client_tax_profiles,portfolio_mandate_bindings",
        "contract_version": "rfc_042_client_tax_profile_v1",
    }


def test_resolve_client_tax_profile_response_orchestrates_repository_reads() -> None:
    async def run_case() -> tuple[object, list[tuple[str, dict[str, object]]]]:
        calls: list[tuple[str, dict[str, object]]] = []

        class Repository:
            async def resolve_discretionary_mandate_binding(
                self, **kwargs: object
            ) -> SimpleNamespace:
                calls.append(("binding", kwargs))
                return _binding()

            async def list_client_tax_profiles(self, **kwargs: object) -> list[SimpleNamespace]:
                calls.append(("profiles", kwargs))
                return [_tax_profile_row()]

        response = await resolve_client_tax_profile_response(
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
            "profiles",
            {
                "portfolio_id": "PB_SG_GLOBAL_BAL_001",
                "client_id": "CIF_SG_000184",
                "as_of_date": date(2026, 5, 3),
                "mandate_id": "MANDATE_PB_SG_GLOBAL_BAL_001",
                "include_inactive_profiles": False,
            },
        ),
    ]


def test_resolve_client_tax_profile_response_skips_rows_without_binding() -> None:
    async def run_case() -> tuple[object | None, list[str]]:
        calls: list[str] = []

        class Repository:
            async def resolve_discretionary_mandate_binding(self, **_: object) -> None:
                calls.append("binding")
                return None

            async def list_client_tax_profiles(self, **_: object) -> list[object]:
                calls.append("profiles")
                raise AssertionError("Unexpected tax-profile read without mandate binding")

        response = await resolve_client_tax_profile_response(
            repository=Repository(),
            portfolio_id="PB_SG_GLOBAL_BAL_001",
            request=_request(),
        )
        return response, calls

    response, calls = asyncio.run(run_case())

    assert response is None
    assert calls == ["binding"]


def test_build_client_tax_profile_response_marks_empty_missing() -> None:
    response = build_client_tax_profile_response(
        portfolio_id="PB_SG_GLOBAL_BAL_001",
        binding=_binding(),
        request=_request(),
        rows=[],
    )

    assert response.profiles == []
    assert response.supportability.state == "INCOMPLETE"
    assert response.supportability.reason == "CLIENT_TAX_PROFILE_EMPTY"
    assert response.supportability.profile_count == 0
    assert response.supportability.missing_data_families == ["client_tax_profile"]
    assert response.data_quality_status == "MISSING"
    assert response.latest_evidence_timestamp == datetime(2026, 5, 3, 8, tzinfo=UTC)
