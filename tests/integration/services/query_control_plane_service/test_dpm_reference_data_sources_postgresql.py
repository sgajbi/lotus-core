"""Real PostgreSQL capacity evidence for bounded DPM source reads."""

from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from portfolio_common.database_models import (
    FxRate,
    Instrument,
    InstrumentEligibilityProfile,
    MarketPrice,
    ModelPortfolioTarget,
    Portfolio,
    PositionLotState,
    Transaction,
)
from sqlalchemy import event as sqlalchemy_event
from sqlalchemy.ext.asyncio import AsyncSession

from src.services.query_control_plane_service.app.infrastructure import (
    dpm_portfolio_state_sources,
)
from src.services.query_control_plane_service.app.infrastructure.dpm_reference_data_sources import (
    SqlAlchemyDpmReferenceDataReader,
)
from tests.test_support.tenant import TEST_TENANT_ID

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


async def test_maximum_supported_eligibility_and_tax_lot_filters_remain_one_statement(
    clean_db,
    async_db_session: AsyncSession,
) -> None:
    as_of_date = date(2026, 4, 10)
    security_ids = [f"DPM_FILTER_{index:04d}" for index in range(1_000)]
    present_ids = [security_ids[0], security_ids[-1]]
    async_db_session.add(
        Portfolio(
            tenant_id=TEST_TENANT_ID,
            portfolio_id="PB_DPM_FILTER_CAPACITY",
            base_currency="USD",
            open_date=date(2020, 1, 1),
            risk_exposure="balanced",
            investment_time_horizon="long_term",
            portfolio_type="discretionary",
            booking_center_code="SG",
            client_id="CLIENT_DPM_FILTER_CAPACITY",
            is_leverage_allowed=False,
            status="ACTIVE",
        )
    )
    async_db_session.add_all(
        [
            Instrument(
                security_id=security_id,
                name=security_id,
                isin=f"DPMFILTER{index:03d}",
                currency="USD",
                product_type="EQUITY",
                asset_class="Equity",
            )
            for index, security_id in enumerate(present_ids)
        ]
    )
    await async_db_session.flush()
    async_db_session.add_all(
        [
            InstrumentEligibilityProfile(
                security_id=security_id,
                eligibility_status="approved",
                product_shelf_status="approved",
                buy_allowed=True,
                sell_allowed=True,
                effective_from=date(2026, 1, 1),
                source_system="capacity-test",
                source_record_id=f"eligibility:{security_id}",
                quality_status="accepted",
            )
            for security_id in present_ids
        ]
    )
    transaction_ids = [f"TX_DPM_FILTER_{index}" for index in range(len(present_ids))]
    async_db_session.add_all(
        [
            Transaction(
                transaction_id=transaction_ids[index],
                portfolio_id="PB_DPM_FILTER_CAPACITY",
                instrument_id=security_id,
                security_id=security_id,
                transaction_type="BUY",
                quantity=Decimal("1"),
                price=Decimal("100"),
                gross_transaction_amount=Decimal("100"),
                trade_currency="USD",
                currency="USD",
                transaction_date=datetime(2026, 4, 1 + index, tzinfo=UTC),
            )
            for index, security_id in enumerate(present_ids)
        ]
    )
    await async_db_session.flush()
    async_db_session.add_all(
        [
            PositionLotState(
                lot_id=f"LOT_DPM_FILTER_{index}",
                source_transaction_id=transaction_ids[index],
                portfolio_id="PB_DPM_FILTER_CAPACITY",
                instrument_id=security_id,
                security_id=security_id,
                acquisition_date=date(2026, 4, 1 + index),
                original_quantity=Decimal("1"),
                open_quantity=Decimal("1"),
                lot_cost_local=Decimal("100"),
                lot_cost_base=Decimal("100"),
                source_system="capacity-test",
            )
            for index, security_id in enumerate(present_ids)
        ]
    )
    await async_db_session.commit()

    bind = async_db_session.bind
    assert bind is not None
    statements: list[str] = []

    def capture_statement(_conn, _cursor, statement, _parameters, _context, _executemany) -> None:
        normalized = statement.lower()
        if normalized.lstrip().startswith("select") and any(
            table in normalized
            for table in ("instrument_eligibility_profiles", "position_lot_state", "instruments")
        ):
            statements.append(normalized)

    sqlalchemy_event.listen(bind.sync_engine, "before_cursor_execute", capture_statement)
    try:
        reference_reader = SqlAlchemyDpmReferenceDataReader(async_db_session)
        state_reader = dpm_portfolio_state_sources.SqlAlchemyDpmPortfolioStateReader(
            async_db_session
        )
        eligibility = await reference_reader.list_instrument_eligibility_profiles(
            security_ids=list(reversed(security_ids)),
            as_of_date=as_of_date,
        )
        lots = await state_reader.list_portfolio_tax_lots(
            portfolio_id="PB_DPM_FILTER_CAPACITY",
            as_of_date=as_of_date,
            security_ids=list(reversed(security_ids)),
            include_closed_lots=False,
            lot_status_filter=None,
            after_sort_key=None,
            limit=1_001,
        )
        known_ids = await state_reader.list_known_instrument_security_ids(
            list(reversed(security_ids))
        )
    finally:
        sqlalchemy_event.remove(bind.sync_engine, "before_cursor_execute", capture_statement)

    assert [record.security_id for record in eligibility] == present_ids
    assert [record.security_id for record in lots] == present_ids
    assert known_ids == set(present_ids)
    assert len(statements) == 3


async def test_model_target_source_threshold_and_overflow_are_bounded(
    clean_db,
    async_db_session: AsyncSession,
) -> None:
    async_db_session.add_all(
        [
            ModelPortfolioTarget(
                model_portfolio_id="MODEL_DPM_CAPACITY",
                model_portfolio_version="2026.04",
                instrument_id=f"MODEL_TARGET_{index:04d}",
                target_weight=Decimal("0"),
                min_weight=Decimal("0"),
                max_weight=Decimal("1"),
                target_status="active",
                effective_from=date(2026, 1, 1),
                source_system="capacity-test",
                source_record_id=f"target:{index:04d}",
                quality_status="accepted",
            )
            for index in range(1_000)
        ]
    )
    await async_db_session.commit()

    bind = async_db_session.bind
    assert bind is not None
    statements: list[str] = []

    def capture_statement(_conn, _cursor, statement, _parameters, _context, _executemany) -> None:
        normalized = statement.lower()
        if normalized.lstrip().startswith("select") and "model_portfolio_targets" in normalized:
            statements.append(normalized)

    sqlalchemy_event.listen(bind.sync_engine, "before_cursor_execute", capture_statement)
    try:
        reader = SqlAlchemyDpmReferenceDataReader(async_db_session)
        supported = await reader.list_model_portfolio_targets(
            model_portfolio_id="MODEL_DPM_CAPACITY",
            model_portfolio_version="2026.04",
            as_of_date=date(2026, 4, 10),
            include_inactive_targets=False,
        )
        async_db_session.add(
            ModelPortfolioTarget(
                model_portfolio_id="MODEL_DPM_CAPACITY",
                model_portfolio_version="2026.04",
                instrument_id="MODEL_TARGET_1000",
                target_weight=Decimal("0"),
                min_weight=Decimal("0"),
                max_weight=Decimal("1"),
                target_status="active",
                effective_from=date(2026, 1, 1),
                source_system="capacity-test",
                source_record_id="target:1000",
                quality_status="accepted",
            )
        )
        await async_db_session.commit()
        overflow = await reader.list_model_portfolio_targets(
            model_portfolio_id="MODEL_DPM_CAPACITY",
            model_portfolio_version="2026.04",
            as_of_date=date(2026, 4, 10),
            include_inactive_targets=False,
        )
    finally:
        sqlalchemy_event.remove(bind.sync_engine, "before_cursor_execute", capture_statement)

    assert supported.limit_exceeded is False
    assert len(supported.records) == 1_000
    assert supported.records[0].instrument_id == "MODEL_TARGET_0000"
    assert supported.records[-1].instrument_id == "MODEL_TARGET_0999"
    assert overflow.limit_exceeded is True
    assert overflow.records == ()
    assert len(statements) == 2
