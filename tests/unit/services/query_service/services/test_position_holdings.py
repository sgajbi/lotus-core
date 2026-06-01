from datetime import date

import pytest

from src.services.query_service.app.services.position_holdings import (
    effective_holdings_as_of_date,
    should_use_default_holdings_as_of_date,
)

pytestmark = pytest.mark.asyncio


async def test_should_use_default_holdings_as_of_date_only_for_booked_latest_reads() -> None:
    assert (
        should_use_default_holdings_as_of_date(
            requested_as_of_date=None,
            include_projected=False,
        )
        is True
    )
    assert (
        should_use_default_holdings_as_of_date(
            requested_as_of_date=date(2025, 1, 1),
            include_projected=False,
        )
        is False
    )
    assert (
        should_use_default_holdings_as_of_date(
            requested_as_of_date=None,
            include_projected=True,
        )
        is False
    )


async def test_effective_holdings_as_of_date_resolves_requested_latest_or_unbounded_scope() -> None:
    assert effective_holdings_as_of_date(
        requested_as_of_date=date(2025, 1, 5),
        latest_business_date=None,
        include_projected=False,
        today=date(2025, 1, 9),
    ) == date(2025, 1, 5)
    assert effective_holdings_as_of_date(
        requested_as_of_date=None,
        latest_business_date=date(2025, 1, 4),
        include_projected=False,
        today=date(2025, 1, 9),
    ) == date(2025, 1, 4)
    assert effective_holdings_as_of_date(
        requested_as_of_date=None,
        latest_business_date=None,
        include_projected=False,
        today=date(2025, 1, 9),
    ) == date(2025, 1, 9)
    assert (
        effective_holdings_as_of_date(
            requested_as_of_date=None,
            latest_business_date=None,
            include_projected=True,
            today=date(2025, 1, 9),
        )
        is None
    )
