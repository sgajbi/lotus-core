"""Query and mapping tests for the client liquidity-evidence SQL adapter."""

from datetime import UTC, date, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.services.query_control_plane_service.app.infrastructure import (
    client_liquidity_evidence_sources,
)

Reader = client_liquidity_evidence_sources.SqlAlchemyClientLiquidityEvidenceReader


class _Result:
    def __init__(self, rows):
        self.rows = rows

    def scalars(self):
        return self

    def all(self):
        return self.rows


def _timestamps() -> dict[str, datetime]:
    value = datetime(2026, 5, 3, 9, tzinfo=UTC)
    return {"observed_at": value, "created_at": value, "updated_at": value}


@pytest.mark.asyncio
async def test_income_query_is_effective_active_ranked_and_typed() -> None:
    session = AsyncMock(spec=AsyncSession)
    session.execute.return_value = _Result(
        [
            SimpleNamespace(
                schedule_id="INCOME_1",
                need_type="RECURRING_INCOME",
                need_status="active",
                amount="12000.2500",
                currency="SGD",
                frequency="monthly",
                start_date=date(2026, 1, 1),
                end_date=None,
                priority="2",
                funding_policy="INCOME_FIRST",
                source_record_id="income:1",
                **_timestamps(),
            )
        ]
    )
    records = await Reader(session).list_income_needs(
        portfolio_id="P1",
        client_id="C1",
        as_of_date=date(2026, 5, 3),
        mandate_id="M1",
        include_inactive_schedules=False,
    )

    assert str(records[0].amount) == "12000.2500"
    assert records[0].priority == 2
    sql = str(session.execute.await_args.args[0].compile(compile_kwargs={"literal_binds": True}))
    assert "row_number() OVER (PARTITION BY client_income_needs_schedules.schedule_id" in sql
    assert "client_income_needs_schedules.need_status = 'active'" in sql
    assert "client_income_needs_schedules.mandate_id IS NULL" in sql


@pytest.mark.asyncio
async def test_reserve_query_preserves_version_precedence_and_mapping() -> None:
    session = AsyncMock(spec=AsyncSession)
    session.execute.return_value = _Result(
        [
            SimpleNamespace(
                reserve_requirement_id="RESERVE_1",
                reserve_type="OPERATING_CASH",
                reserve_status="active",
                required_amount="250000.0000",
                currency="SGD",
                horizon_days="180",
                priority="1",
                policy_source="IPS_2026",
                effective_from=date(2026, 1, 1),
                effective_to=None,
                requirement_version="3",
                source_record_id="reserve:3",
                **_timestamps(),
            )
        ]
    )
    records = await Reader(session).list_reserve_requirements(
        portfolio_id="P1",
        client_id="C1",
        as_of_date=date(2026, 5, 3),
        mandate_id=None,
        include_inactive_requirements=False,
    )

    assert records[0].requirement_version == 3
    assert records[0].horizon_days == 180
    sql = str(session.execute.await_args.args[0].compile(compile_kwargs={"literal_binds": True}))
    assert "liquidity_reserve_requirements.requirement_version DESC" in sql
    assert "liquidity_reserve_requirements.reserve_status = 'active'" in sql


@pytest.mark.asyncio
async def test_withdrawal_query_applies_inclusive_horizon_and_stable_order() -> None:
    session = AsyncMock(spec=AsyncSession)
    session.execute.return_value = _Result(
        [
            SimpleNamespace(
                withdrawal_schedule_id="WITHDRAWAL_1",
                withdrawal_type="CAPITAL_CALL",
                withdrawal_status="active",
                amount="50000.0000",
                currency="SGD",
                scheduled_date=date(2026, 6, 1),
                recurrence_frequency=None,
                purpose_code="PRIVATE_MARKET_CALL",
                source_record_id="withdrawal:1",
                **_timestamps(),
            )
        ]
    )
    records = await Reader(session).list_planned_withdrawals(
        portfolio_id="P1",
        client_id="C1",
        as_of_date=date(2026, 5, 3),
        horizon_days=30,
        mandate_id="M1",
        include_inactive_withdrawals=False,
    )

    assert str(records[0].amount) == "50000.0000"
    sql = str(session.execute.await_args.args[0].compile(compile_kwargs={"literal_binds": True}))
    assert "planned_withdrawal_schedules.scheduled_date >= '2026-05-03'" in sql
    assert "planned_withdrawal_schedules.scheduled_date <= '2026-06-02'" in sql
    assert "planned_withdrawal_schedules.withdrawal_status = 'active'" in sql
    assert "ORDER BY planned_withdrawal_schedules.scheduled_date ASC" in sql


@pytest.mark.parametrize(
    ("method_name", "include_name"),
    [
        ("list_income_needs", "include_inactive_schedules"),
        ("list_reserve_requirements", "include_inactive_requirements"),
        ("list_planned_withdrawals", "include_inactive_withdrawals"),
    ],
)
@pytest.mark.asyncio
async def test_inactive_filter_can_be_explicitly_removed(
    method_name: str, include_name: str
) -> None:
    session = AsyncMock(spec=AsyncSession)
    session.execute.return_value = _Result([])
    kwargs = {
        "portfolio_id": "P1",
        "client_id": "C1",
        "as_of_date": date(2026, 5, 3),
        "mandate_id": None,
        include_name: True,
    }
    if method_name == "list_planned_withdrawals":
        kwargs["horizon_days"] = 30
    await getattr(Reader(session), method_name)(**kwargs)
    sql = str(session.execute.await_args.args[0].compile(compile_kwargs={"literal_binds": True}))
    assert " = 'active'" not in sql
