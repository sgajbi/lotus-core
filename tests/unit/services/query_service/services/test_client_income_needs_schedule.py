from datetime import UTC, date, datetime
from decimal import Decimal
from types import SimpleNamespace

from src.services.query_service.app.dtos.reference_integration_dto import (
    ClientIncomeNeedsScheduleRequest,
)
from src.services.query_service.app.services.client_income_needs_schedule import (
    build_client_income_needs_schedule_response,
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
