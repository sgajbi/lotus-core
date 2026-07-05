from datetime import date
from unittest.mock import AsyncMock

import pytest
from portfolio_common.config import DEFAULT_BUSINESS_CALENDAR_CODE

from src.services.query_service.app.services.transaction_dates import (
    realized_tax_effective_as_of_date,
    transaction_ledger_effective_as_of_date,
)

pytestmark = pytest.mark.asyncio


async def test_transaction_ledger_effective_as_of_date_uses_explicit_date() -> None:
    repository = AsyncMock()

    effective_as_of_date = await transaction_ledger_effective_as_of_date(
        repository=repository,
        as_of_date=date(2025, 1, 14),
        include_projected=False,
    )

    assert effective_as_of_date == date(2025, 1, 14)
    repository.get_latest_business_date.assert_not_awaited()


async def test_transaction_ledger_effective_as_of_date_skips_default_for_projected_reads() -> None:
    repository = AsyncMock()

    effective_as_of_date = await transaction_ledger_effective_as_of_date(
        repository=repository,
        as_of_date=None,
        include_projected=True,
    )

    assert effective_as_of_date is None
    repository.get_latest_business_date.assert_not_awaited()


async def test_transaction_ledger_effective_as_of_date_uses_latest_business_date() -> None:
    repository = AsyncMock()
    repository.get_latest_business_date.return_value = date(2025, 1, 15)

    effective_as_of_date = await transaction_ledger_effective_as_of_date(
        repository=repository,
        as_of_date=None,
        include_projected=False,
    )

    assert effective_as_of_date == date(2025, 1, 15)
    repository.get_latest_business_date.assert_awaited_once_with(
        calendar_code=DEFAULT_BUSINESS_CALENDAR_CODE
    )


async def test_transaction_ledger_effective_as_of_date_falls_back_to_today() -> None:
    repository = AsyncMock()
    repository.get_latest_business_date.return_value = None

    effective_as_of_date = await transaction_ledger_effective_as_of_date(
        repository=repository,
        as_of_date=None,
        include_projected=False,
        today=lambda: date(2025, 1, 20),
    )

    assert effective_as_of_date == date(2025, 1, 20)


async def test_realized_tax_effective_as_of_date_uses_explicit_date() -> None:
    repository = AsyncMock()

    effective_as_of_date = await realized_tax_effective_as_of_date(
        repository=repository,
        as_of_date=date(2025, 1, 14),
    )

    assert effective_as_of_date == date(2025, 1, 14)
    repository.get_latest_business_date.assert_not_awaited()


async def test_realized_tax_effective_as_of_date_uses_latest_business_date() -> None:
    repository = AsyncMock()
    repository.get_latest_business_date.return_value = date(2025, 1, 15)

    effective_as_of_date = await realized_tax_effective_as_of_date(
        repository=repository,
        as_of_date=None,
    )

    assert effective_as_of_date == date(2025, 1, 15)
    repository.get_latest_business_date.assert_awaited_once_with(
        calendar_code=DEFAULT_BUSINESS_CALENDAR_CODE
    )


async def test_realized_tax_effective_as_of_date_falls_back_to_today() -> None:
    repository = AsyncMock()
    repository.get_latest_business_date.return_value = None

    effective_as_of_date = await realized_tax_effective_as_of_date(
        repository=repository,
        as_of_date=None,
        today=lambda: date(2025, 1, 20),
    )

    assert effective_as_of_date == date(2025, 1, 20)
