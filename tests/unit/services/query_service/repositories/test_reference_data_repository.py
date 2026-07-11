"""SQL contract tests for Query Service FX reference reads."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.services.query_service.app.repositories.reference_data_repository import (
    ReferenceDataRepository,
)


class _FakeExecuteResult:
    def __init__(self, rows: list[object]):
        self._rows = rows

    def scalars(self) -> _FakeExecuteResult:
        return self

    def all(self) -> list[object]:
        return self._rows


@pytest.mark.asyncio
async def test_get_fx_rates_normalizes_currency_and_ignores_invalid_rates() -> None:
    db = AsyncMock(spec=AsyncSession)
    db.execute.return_value = _FakeExecuteResult(
        [
            SimpleNamespace(rate_date=date(2026, 1, 1), rate=Decimal("1.1")),
            SimpleNamespace(rate_date=date(2026, 1, 2), rate=" "),
            SimpleNamespace(rate_date=date(2026, 1, 3), rate=None),
            SimpleNamespace(rate_date=date(2026, 1, 4), rate=" 1.4 "),
        ]
    )
    repository = ReferenceDataRepository(db)

    rates = await repository.get_fx_rates(
        from_currency=" eur ",
        to_currency=" usd ",
        start_date=date(2026, 1, 1),
        end_date=date(2026, 1, 4),
    )

    assert rates == {
        date(2026, 1, 1): Decimal("1.1"),
        date(2026, 1, 4): Decimal("1.4"),
    }
    statement = db.execute.await_args.args[0]
    sql = str(statement.compile(compile_kwargs={"literal_binds": True}))
    assert "upper(trim(fx_rates.from_currency)) = 'EUR'" in sql
    assert "upper(trim(fx_rates.to_currency)) = 'USD'" in sql
    assert "fx_rates.rate_date >= '2026-01-01'" in sql
    assert "fx_rates.rate_date <= '2026-01-04'" in sql
    assert "fx_rates.rate_date ASC" in sql
