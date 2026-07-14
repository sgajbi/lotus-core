"""Verify effective-dated SQLAlchemy FX rate lookup behavior."""

from datetime import date
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest
from portfolio_common.database_models import FxRate

from src.services.portfolio_transaction_processing_service.app.domain.cost_basis import (
    EffectiveFxRate,
)
from src.services.portfolio_transaction_processing_service.app.infrastructure.cost_basis import (
    SqlAlchemyCostBasisFxRateRepository,
)

pytestmark = pytest.mark.asyncio


async def test_get_fx_rate_window_fetches_one_seed_plus_bounded_effective_window() -> None:
    db_session = AsyncMock()
    repository = SqlAlchemyCostBasisFxRateRepository(db_session)
    execute_result = MagicMock()
    execute_result.scalars.return_value.all.return_value = [
        FxRate(
            from_currency="EUR",
            to_currency="SGD",
            rate_date=date(2026, 4, 1),
            rate=Decimal("1.40"),
        ),
        FxRate(
            from_currency="EUR",
            to_currency="SGD",
            rate_date=date(2026, 4, 10),
            rate=Decimal("1.45"),
        ),
    ]
    db_session.execute.return_value = execute_result

    rates = await repository.get_fx_rate_window(
        " eur ",
        " sgd ",
        start_date=date(2026, 4, 5),
        end_date=date(2026, 4, 15),
    )

    assert rates == [
        EffectiveFxRate(effective_date=date(2026, 4, 1), rate=Decimal("1.40")),
        EffectiveFxRate(effective_date=date(2026, 4, 10), rate=Decimal("1.45")),
    ]
    compiled_query = str(
        db_session.execute.call_args.args[0].compile(compile_kwargs={"literal_binds": True})
    ).lower()
    assert "upper(trim(fx_rates.from_currency)) = 'eur'" in compiled_query
    assert "upper(trim(fx_rates.to_currency)) = 'sgd'" in compiled_query
    assert "fx_rates.rate_date <= '2026-04-15'" in compiled_query
    assert "fx_rates.rate_date >= '2026-04-05'" in compiled_query
    assert "max(fx_rates_1.rate_date)" in compiled_query
    assert "fx_rates_1.rate_date < '2026-04-05'" in compiled_query
    assert "order by fx_rates.rate_date asc" in compiled_query


async def test_get_fx_rate_window_rejects_reversed_date_bounds() -> None:
    repository = SqlAlchemyCostBasisFxRateRepository(AsyncMock())

    with pytest.raises(ValueError, match="start_date must be on or before end_date"):
        await repository.get_fx_rate_window(
            "EUR",
            "SGD",
            start_date=date(2026, 4, 15),
            end_date=date(2026, 4, 5),
        )
