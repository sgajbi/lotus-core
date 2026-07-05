from collections.abc import Callable
from datetime import date
from typing import Any

from portfolio_common.config import DEFAULT_BUSINESS_CALENDAR_CODE


async def transaction_ledger_effective_as_of_date(
    *,
    repository: Any,
    as_of_date: date | None,
    include_projected: bool,
    today: Callable[[], date] = date.today,
) -> date | None:
    if as_of_date is not None or include_projected:
        return as_of_date

    return (
        await repository.get_latest_business_date(calendar_code=DEFAULT_BUSINESS_CALENDAR_CODE)
        or today()
    )


async def realized_tax_effective_as_of_date(
    *,
    repository: Any,
    as_of_date: date | None,
    today: Callable[[], date] = date.today,
) -> date:
    if as_of_date is not None:
        return as_of_date

    return (
        await repository.get_latest_business_date(calendar_code=DEFAULT_BUSINESS_CALENDAR_CODE)
        or today()
    )
