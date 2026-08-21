"""Real PostgreSQL capacity evidence for DPM market-data source reads."""

from datetime import date
from decimal import Decimal

import pytest
from portfolio_common.database_models import FxRate, MarketPrice
from sqlalchemy import event as sqlalchemy_event
from sqlalchemy.ext.asyncio import AsyncSession

from src.services.query_control_plane_service.app.infrastructure.dpm_reference_data_sources import (
    SqlAlchemyDpmReferenceDataReader,
)

pytestmark = [pytest.mark.asyncio, pytest.mark.db_direct]


def _currency_code(index: int) -> str:
    return "".join(
        (
            chr(65 + (index // (26 * 26)) % 26),
            chr(65 + (index // 26) % 26),
            chr(65 + index % 26),
        )
    )


async def test_maximum_supported_market_data_reads_are_one_statement_each(
    clean_db,
    async_db_session: AsyncSession,
) -> None:
    as_of_date = date(2026, 4, 10)
    security_ids = [f"DPM_SEC_{index:04d}" for index in range(1_000)]
    currency_pairs = [(_currency_code(index), "ZZZ") for index in range(1_000)]
    async_db_session.add_all(
        [
            MarketPrice(
                security_id=security_id,
                price_date=as_of_date,
                price=Decimal("100.0000000000") + index,
                currency="USD",
            )
            for index, security_id in enumerate(security_ids)
        ]
    )
    async_db_session.add_all(
        [
            FxRate(
                from_currency=base,
                to_currency=quote,
                rate_date=as_of_date,
                rate=Decimal("1.0000000000") + Decimal(index) / Decimal("10000"),
            )
            for index, (base, quote) in enumerate(currency_pairs)
        ]
    )
    await async_db_session.commit()

    bind = async_db_session.bind
    assert bind is not None
    statements: list[str] = []

    def capture_statement(_conn, _cursor, statement, _parameters, _context, _executemany) -> None:
        normalized = statement.lower()
        if normalized.lstrip().startswith("select") and (
            "market_prices" in normalized or "fx_rates" in normalized
        ):
            statements.append(normalized)

    sqlalchemy_event.listen(bind.sync_engine, "before_cursor_execute", capture_statement)
    try:
        reader = SqlAlchemyDpmReferenceDataReader(async_db_session)
        prices = await reader.list_latest_market_prices(
            security_ids=list(reversed(security_ids)),
            as_of_date=as_of_date,
        )
        rates = await reader.list_latest_fx_rates(
            currency_pairs=list(reversed(currency_pairs)),
            as_of_date=as_of_date,
        )
    finally:
        sqlalchemy_event.remove(bind.sync_engine, "before_cursor_execute", capture_statement)

    assert [record.security_id for record in prices] == security_ids
    assert [(record.from_currency, record.to_currency) for record in rates] == currency_pairs
    assert len(statements) == 2
