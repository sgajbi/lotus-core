import asyncio
from datetime import UTC, date, datetime
from decimal import Decimal
from types import SimpleNamespace

from src.services.query_service.app.dtos.reference_integration_dto import (
    PlannedWithdrawalScheduleRequest,
)
from src.services.query_service.app.services.planned_withdrawal_schedule import (
    build_planned_withdrawal_schedule_response,
    resolve_planned_withdrawal_schedule_response,
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


def _withdrawal_row() -> SimpleNamespace:
    return SimpleNamespace(
        withdrawal_schedule_id="WITHDRAWAL_Q3_001",
        withdrawal_type="PLANNED_WITHDRAWAL",
        withdrawal_status="active",
        amount=Decimal("50000.0000"),
        currency="SGD",
        scheduled_date=date(2026, 7, 15),
        recurrence_frequency="QUARTERLY",
        purpose_code="CLIENT_SPENDING",
        source_record_id="withdrawal:1",
        observed_at=datetime(2026, 5, 3, 9, tzinfo=UTC),
        updated_at=datetime(2026, 5, 3, 9, tzinfo=UTC),
    )


def _request() -> PlannedWithdrawalScheduleRequest:
    return PlannedWithdrawalScheduleRequest(
        as_of_date=date(2026, 5, 3),
        tenant_id="default",
        mandate_id="MANDATE_PB_SG_GLOBAL_BAL_001",
        horizon_days=180,
    )


def test_build_planned_withdrawal_schedule_response_marks_ready() -> None:
    response = build_planned_withdrawal_schedule_response(
        portfolio_id="PB_SG_GLOBAL_BAL_001",
        binding=_binding(),
        request=_request(),
        rows=[_withdrawal_row()],
    )

    assert response.product_name == "PlannedWithdrawalSchedule"
    assert response.client_id == "CIF_SG_000184"
    assert response.horizon_days == 180
    assert response.supportability.state == "READY"
    assert response.supportability.reason == "PLANNED_WITHDRAWAL_SCHEDULE_READY"
    assert response.supportability.withdrawal_count == 1
    assert response.supportability.missing_data_families == []
    assert response.withdrawals[0].amount == Decimal("50000.0000")
    assert response.withdrawals[0].currency == "SGD"
    assert response.withdrawals[0].scheduled_date == date(2026, 7, 15)
    assert response.data_quality_status == "ACCEPTED"
    assert response.latest_evidence_timestamp == datetime(2026, 5, 3, 9, tzinfo=UTC)
    assert response.source_batch_fingerprint is not None
    assert response.snapshot_id is not None
    assert response.snapshot_id.startswith("planned_withdrawal_schedule:")
    assert response.lineage == {
        "source_system": "lotus-core-query-service",
        "source_table": "planned_withdrawal_schedules,portfolio_mandate_bindings",
        "contract_version": "rfc_042_planned_withdrawal_schedule_v1",
    }


def test_resolve_planned_withdrawal_schedule_response_orchestrates_repository_reads() -> None:
    async def run_case() -> tuple[object, list[tuple[str, dict[str, object]]]]:
        calls: list[tuple[str, dict[str, object]]] = []

        class Repository:
            async def resolve_discretionary_mandate_binding(
                self, **kwargs: object
            ) -> SimpleNamespace:
                calls.append(("binding", kwargs))
                return _binding()

            async def list_planned_withdrawal_schedules(
                self, **kwargs: object
            ) -> list[SimpleNamespace]:
                calls.append(("withdrawals", kwargs))
                return [_withdrawal_row()]

        response = await resolve_planned_withdrawal_schedule_response(
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
            "withdrawals",
            {
                "portfolio_id": "PB_SG_GLOBAL_BAL_001",
                "client_id": "CIF_SG_000184",
                "as_of_date": date(2026, 5, 3),
                "horizon_days": 180,
                "mandate_id": "MANDATE_PB_SG_GLOBAL_BAL_001",
                "include_inactive_withdrawals": False,
            },
        ),
    ]


def test_resolve_planned_withdrawal_schedule_response_skips_rows_without_binding() -> None:
    async def run_case() -> tuple[object | None, list[str]]:
        calls: list[str] = []

        class Repository:
            async def resolve_discretionary_mandate_binding(self, **_: object) -> None:
                calls.append("binding")
                return None

            async def list_planned_withdrawal_schedules(self, **_: object) -> list[object]:
                calls.append("withdrawals")
                raise AssertionError("Unexpected withdrawal read without mandate binding")

        response = await resolve_planned_withdrawal_schedule_response(
            repository=Repository(),
            portfolio_id="PB_SG_GLOBAL_BAL_001",
            request=_request(),
        )
        return response, calls

    response, calls = asyncio.run(run_case())

    assert response is None
    assert calls == ["binding"]


def test_build_planned_withdrawal_schedule_response_marks_empty_missing() -> None:
    response = build_planned_withdrawal_schedule_response(
        portfolio_id="PB_SG_GLOBAL_BAL_001",
        binding=_binding(),
        request=_request(),
        rows=[],
    )

    assert response.withdrawals == []
    assert response.supportability.state == "INCOMPLETE"
    assert response.supportability.reason == "PLANNED_WITHDRAWAL_SCHEDULE_EMPTY"
    assert response.supportability.withdrawal_count == 0
    assert response.supportability.missing_data_families == ["planned_withdrawal_schedule"]
    assert response.data_quality_status == "MISSING"
    assert response.latest_evidence_timestamp == datetime(2026, 5, 3, 8, tzinfo=UTC)
