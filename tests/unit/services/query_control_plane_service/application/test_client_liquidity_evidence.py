"""Behavior tests for QCP-owned client liquidity evidence."""

from datetime import UTC, date, datetime
from decimal import Decimal

import pytest

from src.services.query_control_plane_service.app.application.client_liquidity_evidence import (
    ClientLiquidityEvidenceService,
)
from src.services.query_control_plane_service.app.contracts.client_liquidity_evidence import (
    ClientIncomeNeedsScheduleRequest,
    LiquidityReserveRequirementRequest,
    PlannedWithdrawalScheduleRequest,
)
from src.services.query_control_plane_service.app.domain.client_liquidity_evidence import (
    ClientIncomeNeedSourceRecord,
    LiquidityReserveRequirementSourceRecord,
    PlannedWithdrawalSourceRecord,
)
from src.services.query_control_plane_service.app.domain.effective_mandate import (
    EffectiveMandateBinding,
)


class _Clock:
    def utc_now(self) -> datetime:
        return datetime(2026, 5, 3, 10, tzinfo=UTC)


class _Reader:
    def __init__(self, binding: EffectiveMandateBinding | None) -> None:
        self.binding = binding
        self.income_needs: list[ClientIncomeNeedSourceRecord] = []
        self.reserve_requirements: list[LiquidityReserveRequirementSourceRecord] = []
        self.withdrawals: list[PlannedWithdrawalSourceRecord] = []
        self.calls: list[tuple[str, dict[str, object]]] = []

    async def resolve(self, **kwargs):
        self.calls.append(("binding", kwargs))
        return self.binding

    async def list_income_needs(self, **kwargs):
        self.calls.append(("income", kwargs))
        return self.income_needs

    async def list_reserve_requirements(self, **kwargs):
        self.calls.append(("reserve", kwargs))
        return self.reserve_requirements

    async def list_planned_withdrawals(self, **kwargs):
        self.calls.append(("withdrawal", kwargs))
        return self.withdrawals


def _binding() -> EffectiveMandateBinding:
    return EffectiveMandateBinding(
        client_id="CIF_SG_000184",
        mandate_id="MANDATE_PB_SG_GLOBAL_BAL_001",
        observed_at=datetime(2026, 5, 3, 8, tzinfo=UTC),
        created_at=datetime(2026, 5, 3, 7, tzinfo=UTC),
        updated_at=datetime(2026, 5, 3, 8, tzinfo=UTC),
    )


def _service(reader: _Reader) -> ClientLiquidityEvidenceService:
    return ClientLiquidityEvidenceService(mandate_reader=reader, reader=reader, clock=_Clock())


def _evidence_time() -> datetime:
    return datetime(2026, 5, 3, 9, tzinfo=UTC)


@pytest.mark.asyncio
async def test_resolves_ready_income_needs_evidence() -> None:
    reader = _Reader(_binding())
    reader.income_needs = [
        ClientIncomeNeedSourceRecord(
            schedule_id="INCOME_NEED_001",
            need_type="RECURRING_INCOME",
            need_status="active",
            amount=Decimal("12000.2500"),
            currency="SGD",
            frequency="monthly",
            start_date=date(2026, 1, 1),
            end_date=None,
            priority=1,
            funding_policy="INCOME_FIRST",
            source_record_id="income:1",
            observed_at=_evidence_time(),
            created_at=_evidence_time(),
            updated_at=_evidence_time(),
        )
    ]
    request = ClientIncomeNeedsScheduleRequest(as_of_date=date(2026, 5, 3), tenant_id="default")

    response = await _service(reader).get_client_income_needs_schedule(
        portfolio_id="PB_SG_GLOBAL_BAL_001", request=request
    )

    assert response is not None
    assert response.schedules[0].amount == Decimal("12000.2500")
    assert response.supportability.state == "READY"
    assert response.generated_at == datetime(2026, 5, 3, 10, tzinfo=UTC)
    assert response.latest_evidence_timestamp == _evidence_time()
    assert response.snapshot_id is not None
    assert reader.calls[1][1]["mandate_id"] == "MANDATE_PB_SG_GLOBAL_BAL_001"


@pytest.mark.asyncio
async def test_resolves_ready_reserve_requirement_evidence() -> None:
    reader = _Reader(_binding())
    reader.reserve_requirements = [
        LiquidityReserveRequirementSourceRecord(
            reserve_requirement_id="RESERVE_001",
            reserve_type="OPERATING_CASH",
            reserve_status="active",
            required_amount=Decimal("250000.0000"),
            currency="SGD",
            horizon_days=180,
            priority=1,
            policy_source="IPS_2026",
            effective_from=date(2026, 1, 1),
            effective_to=None,
            requirement_version=3,
            source_record_id="reserve:3",
            observed_at=_evidence_time(),
            created_at=_evidence_time(),
            updated_at=_evidence_time(),
        )
    ]

    response = await _service(reader).get_liquidity_reserve_requirement(
        portfolio_id="PB_SG_GLOBAL_BAL_001",
        request=LiquidityReserveRequirementRequest(as_of_date=date(2026, 5, 3)),
    )

    assert response is not None
    assert response.requirements[0].required_amount == Decimal("250000.0000")
    assert response.requirements[0].requirement_version == 3
    assert response.supportability.reason == "LIQUIDITY_RESERVE_REQUIREMENT_READY"


@pytest.mark.asyncio
async def test_resolves_ready_withdrawals_and_carries_horizon() -> None:
    reader = _Reader(_binding())
    reader.withdrawals = [
        PlannedWithdrawalSourceRecord(
            withdrawal_schedule_id="WITHDRAWAL_001",
            withdrawal_type="CAPITAL_CALL",
            withdrawal_status="active",
            amount=Decimal("50000.0000"),
            currency="SGD",
            scheduled_date=date(2026, 6, 1),
            recurrence_frequency=None,
            purpose_code="PRIVATE_MARKET_CALL",
            source_record_id="withdrawal:1",
            observed_at=_evidence_time(),
            created_at=_evidence_time(),
            updated_at=_evidence_time(),
        )
    ]
    request = PlannedWithdrawalScheduleRequest(as_of_date=date(2026, 5, 3), horizon_days=180)

    first = await _service(reader).get_planned_withdrawal_schedule(
        portfolio_id="PB_SG_GLOBAL_BAL_001", request=request
    )
    second = await _service(reader).get_planned_withdrawal_schedule(
        portfolio_id="PB_SG_GLOBAL_BAL_001", request=request
    )

    assert first is not None and second is not None
    assert first.horizon_days == 180
    assert first.withdrawals[0].purpose_code == "PRIVATE_MARKET_CALL"
    assert first.snapshot_id == second.snapshot_id
    assert reader.calls[1][1]["horizon_days"] == 180


@pytest.mark.parametrize(
    ("method_name", "request_model", "missing_family"),
    [
        (
            "get_client_income_needs_schedule",
            ClientIncomeNeedsScheduleRequest(as_of_date=date(2026, 5, 3)),
            "client_income_needs_schedule",
        ),
        (
            "get_liquidity_reserve_requirement",
            LiquidityReserveRequirementRequest(as_of_date=date(2026, 5, 3)),
            "liquidity_reserve_requirement",
        ),
        (
            "get_planned_withdrawal_schedule",
            PlannedWithdrawalScheduleRequest(as_of_date=date(2026, 5, 3)),
            "planned_withdrawal_schedule",
        ),
    ],
)
@pytest.mark.asyncio
async def test_empty_evidence_is_explicitly_incomplete(
    method_name: str, request_model: object, missing_family: str
) -> None:
    service = _service(_Reader(_binding()))
    response = await getattr(service, method_name)(portfolio_id="P1", request=request_model)

    assert response.supportability.state == "INCOMPLETE"
    assert response.supportability.missing_data_families == [missing_family]
    assert response.data_quality_status == "MISSING"
    assert response.latest_evidence_timestamp == datetime(2026, 5, 3, 8, tzinfo=UTC)


@pytest.mark.asyncio
async def test_missing_binding_skips_all_evidence_reads() -> None:
    reader = _Reader(None)
    response = await _service(reader).get_client_income_needs_schedule(
        portfolio_id="PB_MISSING",
        request=ClientIncomeNeedsScheduleRequest(as_of_date=date(2026, 5, 3)),
    )

    assert response is None
    assert [name for name, _ in reader.calls] == ["binding"]
