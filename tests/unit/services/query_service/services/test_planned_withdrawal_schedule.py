from datetime import UTC, date, datetime
from decimal import Decimal
from types import SimpleNamespace

from src.services.query_service.app.dtos.reference_integration_dto import (
    PlannedWithdrawalScheduleRequest,
)
from src.services.query_service.app.services.planned_withdrawal_schedule import (
    build_planned_withdrawal_schedule_response,
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
