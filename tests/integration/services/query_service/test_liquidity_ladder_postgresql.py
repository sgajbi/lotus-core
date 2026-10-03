"""Registered HTTP and PostgreSQL proof for liquidity valuation qualification."""

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import httpx
import pytest
from portfolio_common.database_models import (
    DailyPositionSnapshot,
    Instrument,
    Portfolio,
    PositionHistory,
    PositionState,
    Transaction,
)
from portfolio_common.db import get_async_db_session
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from src.services.query_service.app.main import app
from tests.test_support.tenant import TEST_LEGAL_BOOK_ID, TEST_TENANT_HEADERS, TEST_TENANT_ID

pytestmark = [pytest.mark.asyncio, pytest.mark.integration_db, pytest.mark.db_direct]

PORTFOLIO_ID = "LIQUIDITY_NULL_VALUE_PG"
SECURITY_ID = "LIQUIDITY_CASH_USD_PG"
TRANSACTION_ID = "LIQUIDITY_CASH_SEED_PG"
AS_OF_DATE = date(2026, 4, 9)
SNAPSHOT_DATE = AS_OF_DATE - timedelta(days=1)


async def _seed_eligible_cash_snapshot(session: AsyncSession) -> None:
    session.add(
        Portfolio(
            portfolio_id=PORTFOLIO_ID,
            tenant_id=TEST_TENANT_ID,
            legal_book_id=TEST_LEGAL_BOOK_ID,
            base_currency="USD",
            open_date=date(2026, 1, 1),
            risk_exposure="MODERATE",
            investment_time_horizon="MEDIUM_TERM",
            portfolio_type="DISCRETIONARY",
            objective="CAPITAL_GROWTH",
            booking_center_code="SG",
            client_id="LIQUIDITY-CLIENT-PG",
            status="ACTIVE",
            is_leverage_allowed=False,
        )
    )
    session.add(
        Instrument(
            security_id=SECURITY_ID,
            name="USD Cash",
            isin="ZZLIQUIDITYCASH1",
            currency="USD",
            product_type="Cash",
            asset_class="CASH",
            liquidity_tier=None,
            country_of_risk="US",
        )
    )
    session.add(
        PositionState(
            portfolio_id=PORTFOLIO_ID,
            security_id=SECURITY_ID,
            epoch=0,
            watermark_date=AS_OF_DATE,
            status="CURRENT",
        )
    )
    session.add(
        Transaction(
            transaction_id=TRANSACTION_ID,
            portfolio_id=PORTFOLIO_ID,
            instrument_id=SECURITY_ID,
            security_id=SECURITY_ID,
            transaction_type="BUY",
            quantity=Decimal("1"),
            price=Decimal("1"),
            gross_transaction_amount=Decimal("1"),
            trade_currency="USD",
            currency="USD",
            transaction_date=datetime(2026, 4, 9, tzinfo=UTC),
        )
    )
    await session.flush()
    session.add(
        PositionHistory(
            portfolio_id=PORTFOLIO_ID,
            security_id=SECURITY_ID,
            transaction_id=TRANSACTION_ID,
            position_date=AS_OF_DATE,
            quantity=Decimal("1"),
            cost_basis=Decimal("1"),
            epoch=0,
        )
    )
    session.add(
        DailyPositionSnapshot(
            portfolio_id=PORTFOLIO_ID,
            security_id=SECURITY_ID,
            date=SNAPSHOT_DATE,
            quantity=Decimal("1"),
            cost_basis=Decimal("1"),
            market_value=None,
            valuation_status="UNVALUED",
            epoch=0,
        )
    )
    await session.commit()


async def _request(client: httpx.AsyncClient, *, tenant_headers: dict[str, str]):
    return await client.get(
        f"/portfolios/{PORTFOLIO_ID}/liquidity-ladder",
        params={"as_of_date": AS_OF_DATE.isoformat(), "horizon_days": 0},
        headers=tenant_headers,
    )


async def test_registered_liquidity_ladder_distinguishes_null_zero_and_positive_postgresql(
    clean_db,
    async_db_session: AsyncSession,
) -> None:
    await _seed_eligible_cash_snapshot(async_db_session)

    async def database_session():
        yield async_db_session

    assert get_async_db_session not in app.dependency_overrides
    app.dependency_overrides[get_async_db_session] = database_session
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app, raise_app_exceptions=False),
            base_url="http://test",
        ) as client:
            unknown = await _request(client, tenant_headers=TEST_TENANT_HEADERS)
            await async_db_session.rollback()

            await async_db_session.execute(
                update(DailyPositionSnapshot)
                .where(
                    DailyPositionSnapshot.portfolio_id == PORTFOLIO_ID,
                    DailyPositionSnapshot.security_id == SECURITY_ID,
                )
                .values(market_value=Decimal("0"), valuation_status="VALUED")
            )
            await async_db_session.commit()
            zero = await _request(client, tenant_headers=TEST_TENANT_HEADERS)
            await async_db_session.rollback()

            await async_db_session.execute(
                update(DailyPositionSnapshot)
                .where(
                    DailyPositionSnapshot.portfolio_id == PORTFOLIO_ID,
                    DailyPositionSnapshot.security_id == SECURITY_ID,
                )
                .values(market_value=Decimal("100"))
            )
            await async_db_session.commit()
            positive = await _request(client, tenant_headers=TEST_TENANT_HEADERS)
            await async_db_session.rollback()

            await async_db_session.execute(
                update(DailyPositionSnapshot)
                .where(
                    DailyPositionSnapshot.portfolio_id == PORTFOLIO_ID,
                    DailyPositionSnapshot.security_id == SECURITY_ID,
                )
                .values(market_value=Decimal("100"), valuation_status="FAILED")
            )
            await async_db_session.commit()
            failed_status = await _request(client, tenant_headers=TEST_TENANT_HEADERS)
            await async_db_session.rollback()

            await async_db_session.execute(
                update(DailyPositionSnapshot)
                .where(
                    DailyPositionSnapshot.portfolio_id == PORTFOLIO_ID,
                    DailyPositionSnapshot.security_id == SECURITY_ID,
                )
                .values(valuation_status="VALUED")
            )
            await async_db_session.execute(
                update(Instrument)
                .where(Instrument.security_id == SECURITY_ID)
                .values(asset_class=" ")
            )
            await async_db_session.commit()
            blank_asset_class = await _request(client, tenant_headers=TEST_TENANT_HEADERS)
            await async_db_session.rollback()
            foreign = await _request(
                client,
                tenant_headers={"X-Tenant-Id": "tenant-foreign"},
            )
    finally:
        app.dependency_overrides.pop(get_async_db_session)

    assert unknown.status_code == 200, unknown.text
    unknown_payload = unknown.json()
    assert unknown_payload["resolved_as_of_date"] == AS_OF_DATE.isoformat()
    assert unknown_payload["data_quality_status"] == "PARTIAL"
    assert unknown_payload["totals"]["opening_cash_balance_portfolio_currency"] is None
    assert unknown_payload["totals"]["projected_cash_available_end_portfolio_currency"] is None
    assert unknown_payload["totals"]["maximum_cash_shortfall_portfolio_currency"] is None
    assert unknown_payload["buckets"][0]["cumulative_cash_available_portfolio_currency"] is None
    assert unknown_payload["buckets"][0]["cash_shortfall_portfolio_currency"] is None
    assert unknown_payload["degradation"]["reason_codes"] == ["CASH_VALUATION_UNAVAILABLE"]
    unknown_detail = unknown_payload["degradation"]["details"][0]
    assert unknown_detail["source_as_of_date"] == SNAPSHOT_DATE.isoformat()
    assert unknown_detail["latest_evidence_timestamp"] is not None

    assert zero.status_code == 200, zero.text
    assert zero.json()["data_quality_status"] == "COMPLETE"
    assert Decimal(zero.json()["totals"]["opening_cash_balance_portfolio_currency"]) == 0
    assert Decimal(zero.json()["totals"]["projected_cash_available_end_portfolio_currency"]) == 0

    assert positive.status_code == 200, positive.text
    assert positive.json()["data_quality_status"] == "COMPLETE"
    assert Decimal(positive.json()["totals"]["opening_cash_balance_portfolio_currency"]) == 100
    assert (
        Decimal(positive.json()["totals"]["projected_cash_available_end_portfolio_currency"]) == 100
    )

    assert failed_status.status_code == 200, failed_status.text
    failed_payload = failed_status.json()
    assert failed_payload["data_quality_status"] == "PARTIAL"
    assert failed_payload["totals"]["opening_cash_balance_portfolio_currency"] is None
    assert failed_payload["degradation"]["reason_codes"] == ["CASH_VALUATION_UNAVAILABLE"]
    assert (
        failed_payload["degradation"]["details"][0]["source_as_of_date"]
        == SNAPSHOT_DATE.isoformat()
    )

    assert blank_asset_class.status_code == 200, blank_asset_class.text
    blank_payload = blank_asset_class.json()
    assert blank_payload["data_quality_status"] == "PARTIAL"
    assert blank_payload["totals"]["opening_cash_balance_portfolio_currency"] is None
    assert blank_payload["totals"]["non_cash_market_value_portfolio_currency"] is None
    assert blank_payload["degradation"]["reason_codes"] == ["INSTRUMENT_CLASSIFICATION_UNAVAILABLE"]
    assert (
        blank_payload["degradation"]["details"][0]["source_as_of_date"] == SNAPSHOT_DATE.isoformat()
    )

    assert foreign.status_code == 404, foreign.text
