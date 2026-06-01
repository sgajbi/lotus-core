import asyncio
from datetime import UTC, date, datetime
from decimal import Decimal
from types import SimpleNamespace

from src.services.query_service.app.dtos.reference_integration_dto import (
    ClientIncomeNeedsScheduleRequest,
)
from src.services.query_service.app.services.client_income_needs_schedule import (
    build_client_income_needs_schedule_response,
    resolve_client_income_needs_schedule_response,
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


def _income_need_row() -> SimpleNamespace:
    return SimpleNamespace(
        schedule_id="INCOME_NEED_MONTHLY_001",
        need_type="LIVING_EXPENSE",
        need_status="active",
        amount=Decimal("25000.0000"),
        currency="SGD",
        frequency="MONTHLY",
        start_date=date(2026, 4, 1),
        end_date=None,
        priority=1,
        funding_policy="POLICY_DPM_SG_BALANCED_V1",
        source_record_id="income-need:1",
        observed_at=datetime(2026, 5, 3, 9, tzinfo=UTC),
        updated_at=datetime(2026, 5, 3, 9, tzinfo=UTC),
    )


def _request() -> ClientIncomeNeedsScheduleRequest:
    return ClientIncomeNeedsScheduleRequest(
        as_of_date=date(2026, 5, 3),
        tenant_id="default",
        mandate_id="MANDATE_PB_SG_GLOBAL_BAL_001",
    )


def test_build_client_income_needs_schedule_response_marks_ready() -> None:
    response = build_client_income_needs_schedule_response(
        portfolio_id="PB_SG_GLOBAL_BAL_001",
        binding=_binding(),
        request=_request(),
        rows=[_income_need_row()],
    )

    assert response.product_name == "ClientIncomeNeedsSchedule"
    assert response.client_id == "CIF_SG_000184"
    assert response.supportability.state == "READY"
    assert response.supportability.reason == "CLIENT_INCOME_NEEDS_SCHEDULE_READY"
    assert response.supportability.schedule_count == 1
    assert response.supportability.missing_data_families == []
    assert response.schedules[0].amount == Decimal("25000.0000")
    assert response.schedules[0].currency == "SGD"
    assert response.data_quality_status == "ACCEPTED"
    assert response.latest_evidence_timestamp == datetime(2026, 5, 3, 9, tzinfo=UTC)
    assert response.source_batch_fingerprint is not None
    assert response.snapshot_id is not None
    assert response.snapshot_id.startswith("client_income_needs_schedule:")
    assert response.lineage == {
        "source_system": "lotus-core-query-service",
        "source_table": "client_income_needs_schedules,portfolio_mandate_bindings",
        "contract_version": "rfc_042_client_income_needs_schedule_v1",
    }


def test_resolve_client_income_needs_schedule_response_orchestrates_repository_reads() -> None:
    async def run_case() -> tuple[object, list[tuple[str, dict[str, object]]]]:
        calls: list[tuple[str, dict[str, object]]] = []

        class Repository:
            async def resolve_discretionary_mandate_binding(
                self, **kwargs: object
            ) -> SimpleNamespace:
                calls.append(("binding", kwargs))
                return _binding()

            async def list_client_income_needs_schedules(
                self, **kwargs: object
            ) -> list[SimpleNamespace]:
                calls.append(("schedules", kwargs))
                return [_income_need_row()]

        response = await resolve_client_income_needs_schedule_response(
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
            "schedules",
            {
                "portfolio_id": "PB_SG_GLOBAL_BAL_001",
                "client_id": "CIF_SG_000184",
                "as_of_date": date(2026, 5, 3),
                "mandate_id": "MANDATE_PB_SG_GLOBAL_BAL_001",
                "include_inactive_schedules": False,
            },
        ),
    ]


def test_resolve_client_income_needs_schedule_response_skips_rows_without_binding() -> None:
    async def run_case() -> tuple[object | None, list[str]]:
        calls: list[str] = []

        class Repository:
            async def resolve_discretionary_mandate_binding(self, **_: object) -> None:
                calls.append("binding")
                return None

            async def list_client_income_needs_schedules(self, **_: object) -> list[object]:
                calls.append("schedules")
                raise AssertionError("Unexpected income schedule read without mandate binding")

        response = await resolve_client_income_needs_schedule_response(
            repository=Repository(),
            portfolio_id="PB_SG_GLOBAL_BAL_001",
            request=_request(),
        )
        return response, calls

    response, calls = asyncio.run(run_case())

    assert response is None
    assert calls == ["binding"]


def test_build_client_income_needs_schedule_response_marks_empty_missing() -> None:
    response = build_client_income_needs_schedule_response(
        portfolio_id="PB_SG_GLOBAL_BAL_001",
        binding=_binding(),
        request=_request(),
        rows=[],
    )

    assert response.schedules == []
    assert response.supportability.state == "INCOMPLETE"
    assert response.supportability.reason == "CLIENT_INCOME_NEEDS_SCHEDULE_EMPTY"
    assert response.supportability.schedule_count == 0
    assert response.supportability.missing_data_families == ["client_income_needs_schedule"]
    assert response.data_quality_status == "MISSING"
    assert response.latest_evidence_timestamp == datetime(2026, 5, 3, 8, tzinfo=UTC)
