from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.services.valuation_orchestrator_service.app.repositories.valuation_repository import (
    ValuationRepository,
)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    (
        "calendar_horizon",
        "is_business_date",
        "snapshot_horizon",
        "job_horizon",
        "expected_membership",
        "expected_horizon",
    ),
    (
        (None, False, None, None, True, None),
        (None, False, date(2026, 4, 9), date(2026, 4, 10), True, date(2026, 4, 10)),
        (date(2026, 4, 13), True, date(2026, 4, 20), None, True, date(2026, 4, 13)),
        (date(2026, 4, 13), False, None, date(2026, 4, 20), False, date(2026, 4, 13)),
    ),
)
async def test_valuation_business_calendar_classification_is_one_atomic_read(
    calendar_horizon: date | None,
    is_business_date: bool,
    snapshot_horizon: date | None,
    job_horizon: date | None,
    expected_membership: bool,
    expected_horizon: date | None,
) -> None:
    database = AsyncMock(spec=AsyncSession)
    result_row = MagicMock()
    result_row.one.return_value = SimpleNamespace(
        calendar_horizon=calendar_horizon,
        is_business_date=is_business_date,
        snapshot_horizon=snapshot_horizon,
        job_horizon=job_horizon,
    )
    database.execute.side_effect = (
        [result_row] if calendar_horizon is not None else [result_row, MagicMock(), result_row]
    )
    repository = ValuationRepository(database)

    result = await repository.classify_valuation_business_date(date(2026, 4, 11))

    assert result.is_business_date is expected_membership
    assert result.latest_business_date == expected_horizon
    assert database.execute.await_count == (1 if calendar_horizon is not None else 3)
    if calendar_horizon is None:
        lock_statement = str(database.execute.await_args_list[1].args[0])
        assert "pg_advisory_xact_lock_shared" in lock_statement


@pytest.mark.asyncio
async def test_valuation_calendar_activation_is_reclassified_under_transaction_lock() -> None:
    database = AsyncMock(spec=AsyncSession)
    absent_result = MagicMock()
    absent_result.one.return_value = SimpleNamespace(
        calendar_horizon=None,
        is_business_date=False,
        snapshot_horizon=date(2026, 4, 10),
        job_horizon=None,
    )
    activated_result = MagicMock()
    activated_result.one.return_value = SimpleNamespace(
        calendar_horizon=date(2026, 4, 13),
        is_business_date=False,
        snapshot_horizon=date(2026, 4, 10),
        job_horizon=None,
    )
    database.execute.side_effect = [absent_result, MagicMock(), activated_result]

    result = await ValuationRepository(database).classify_valuation_business_date(date(2026, 4, 11))

    assert result.is_business_date is False
    assert result.latest_business_date == date(2026, 4, 13)
    assert database.execute.await_count == 3
