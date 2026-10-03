"""Registered HTTP and PostgreSQL proof for allocation valuation coverage."""

from datetime import UTC, date, datetime
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
from sqlalchemy import delete, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.services.query_service.app.main import app
from tests.test_support.tenant import TEST_LEGAL_BOOK_ID, TEST_TENANT_HEADERS, TEST_TENANT_ID

pytestmark = [pytest.mark.asyncio, pytest.mark.integration_db, pytest.mark.db_direct]

PORTFOLIO_ID = "ALLOCATION_VALUATION_COVERAGE_PG"
AS_OF_DATE = date(2026, 4, 9)
EQUITY_ID = "ALLOCATION_EQUITY_PG"
BOND_ID = "ALLOCATION_BOND_PG"


async def _seed_allocation_snapshots(session: AsyncSession) -> None:
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
            client_id="ALLOCATION-CLIENT-PG",
            status="ACTIVE",
            is_leverage_allowed=False,
        )
    )
    session.add_all(
        [
            Instrument(
                security_id=EQUITY_ID,
                name="Allocation Equity",
                isin="ZZALLOCATIONEQ1",
                currency="USD",
                product_type="Equity",
                asset_class="EQUITY",
                country_of_risk="US",
            ),
            Instrument(
                security_id=BOND_ID,
                name="Allocation Bond",
                isin="ZZALLOCATIONBD1",
                currency="USD",
                product_type="Bond",
                asset_class="BOND",
                country_of_risk="US",
            ),
        ]
    )
    for index, security_id in enumerate((EQUITY_ID, BOND_ID), start=1):
        transaction_id = f"ALLOCATION-SEED-{index}"
        session.add(
            PositionState(
                portfolio_id=PORTFOLIO_ID,
                security_id=security_id,
                epoch=0,
                watermark_date=AS_OF_DATE,
                status="CURRENT",
            )
        )
        session.add(
            Transaction(
                transaction_id=transaction_id,
                portfolio_id=PORTFOLIO_ID,
                instrument_id=security_id,
                security_id=security_id,
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
                security_id=security_id,
                transaction_id=transaction_id,
                position_date=AS_OF_DATE,
                quantity=Decimal("1"),
                cost_basis=Decimal("1"),
                epoch=0,
            )
        )
    session.add_all(
        [
            DailyPositionSnapshot(
                portfolio_id=PORTFOLIO_ID,
                security_id=EQUITY_ID,
                date=AS_OF_DATE,
                quantity=Decimal("1"),
                cost_basis=Decimal("100"),
                market_value=Decimal("100"),
                valuation_status="VALUED_CURRENT",
                epoch=0,
            ),
            DailyPositionSnapshot(
                portfolio_id=PORTFOLIO_ID,
                security_id=BOND_ID,
                date=AS_OF_DATE,
                quantity=Decimal("1"),
                cost_basis=Decimal("100"),
                market_value=None,
                valuation_status="UNVALUED",
                epoch=0,
            ),
        ]
    )
    await session.commit()


async def _request(client: httpx.AsyncClient) -> httpx.Response:
    return await client.post(
        "/reporting/asset-allocation/query",
        json={
            "scope": {"portfolio_id": PORTFOLIO_ID},
            "as_of_date": AS_OF_DATE.isoformat(),
            "dimensions": ["asset_class"],
            "look_through_mode": "direct_only",
            "contributor_limit_per_bucket": 20,
        },
        headers=TEST_TENANT_HEADERS,
    )


def _buckets(payload: dict) -> dict[str, dict]:
    return {bucket["dimension_value"]: bucket for bucket in payload["views"][0]["buckets"]}


async def test_registered_allocation_distinguishes_unknown_zero_signed_and_failed_postgresql(
    clean_db,
    async_db_session: AsyncSession,
) -> None:
    await _seed_allocation_snapshots(async_db_session)

    async def database_session():
        yield async_db_session

    assert get_async_db_session not in app.dependency_overrides
    app.dependency_overrides[get_async_db_session] = database_session
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app, raise_app_exceptions=False),
            base_url="http://test",
        ) as client:
            unknown = await _request(client)
            await async_db_session.rollback()

            await async_db_session.execute(
                update(DailyPositionSnapshot)
                .where(DailyPositionSnapshot.security_id == BOND_ID)
                .values(market_value=Decimal("0"), valuation_status="VALUED_CURRENT")
            )
            await async_db_session.commit()
            async_db_session.expire_all()
            zero = await _request(client)
            await async_db_session.rollback()

            await async_db_session.execute(
                update(DailyPositionSnapshot)
                .where(DailyPositionSnapshot.security_id == BOND_ID)
                .values(market_value=Decimal("-20"))
            )
            await async_db_session.commit()
            async_db_session.expire_all()
            signed = await _request(client)
            await async_db_session.rollback()

            await async_db_session.execute(
                update(DailyPositionSnapshot)
                .where(DailyPositionSnapshot.security_id == BOND_ID)
                .values(market_value=Decimal("100"), valuation_status="FAILED")
            )
            await async_db_session.commit()
            async_db_session.expire_all()
            failed = await _request(client)
            await async_db_session.rollback()

            await async_db_session.execute(
                update(DailyPositionSnapshot)
                .where(DailyPositionSnapshot.security_id.in_([EQUITY_ID, BOND_ID]))
                .values(market_value=None, valuation_status="UNVALUED")
            )
            await async_db_session.commit()
            async_db_session.expire_all()
            all_missing = await _request(client)
            await async_db_session.rollback()

            await async_db_session.execute(
                delete(DailyPositionSnapshot).where(DailyPositionSnapshot.security_id == BOND_ID)
            )
            await async_db_session.commit()
            async_db_session.expire_all()
            missing_snapshot = await _request(client)
    finally:
        app.dependency_overrides.pop(get_async_db_session)

    assert unknown.status_code == 200, unknown.text
    unknown_payload = unknown.json()
    unknown_buckets = _buckets(unknown_payload)
    assert unknown_payload["valuation_coverage"] == {
        "coverage_state": "PARTIAL",
        "coverage_reason": "market_value_missing",
        "snapshot_row_count": 2,
        "expected_open_position_count": 2,
        "valued_position_count": 1,
        "unvalued_position_count": 1,
    }
    assert unknown_payload["total_market_value_reporting_currency"] is None
    assert Decimal(unknown_buckets["EQUITY"]["market_value_reporting_currency"]) == 100
    assert unknown_buckets["EQUITY"]["weight"] is None
    assert unknown_buckets["BOND"]["market_value_reporting_currency"] is None
    assert unknown_buckets["BOND"]["weight"] is None
    assert unknown_buckets["BOND"]["contributors"][0]["market_value_reporting_currency"] is None

    assert zero.status_code == 200, zero.text
    zero_payload = zero.json()
    zero_buckets = _buckets(zero_payload)
    assert zero_payload["valuation_coverage"]["coverage_state"] == "COMPLETE"
    assert Decimal(zero_payload["total_market_value_reporting_currency"]) == 100
    assert Decimal(zero_buckets["EQUITY"]["weight"]) == 1
    assert Decimal(zero_buckets["BOND"]["weight"]) == 0
    assert (
        unknown_payload["calculation_lineage"]["input_content_hash"]
        != zero_payload["calculation_lineage"]["input_content_hash"]
    )

    assert signed.status_code == 200, signed.text
    signed_payload = signed.json()
    signed_buckets = _buckets(signed_payload)
    assert Decimal(signed_payload["total_market_value_reporting_currency"]) == 80
    assert Decimal(signed_buckets["EQUITY"]["weight"]) == Decimal("1.25")
    assert Decimal(signed_buckets["BOND"]["weight"]) == Decimal("-0.25")

    assert failed.status_code == 200, failed.text
    failed_payload = failed.json()
    assert failed_payload["valuation_coverage"]["coverage_reason"] == (
        "valuation_status_not_valued"
    )
    assert failed_payload["total_market_value_reporting_currency"] is None
    assert _buckets(failed_payload)["BOND"]["market_value_reporting_currency"] is None

    assert all_missing.status_code == 200, all_missing.text
    all_missing_payload = all_missing.json()
    assert all_missing_payload["valuation_coverage"]["valued_position_count"] == 0
    assert all_missing_payload["valuation_coverage"]["unvalued_position_count"] == 2
    assert all_missing_payload["total_market_value_reporting_currency"] is None
    assert all(
        bucket["market_value_reporting_currency"] is None and bucket["weight"] is None
        for bucket in _buckets(all_missing_payload).values()
    )

    assert missing_snapshot.status_code == 200, missing_snapshot.text
    missing_snapshot_payload = missing_snapshot.json()
    assert missing_snapshot_payload["valuation_coverage"] == {
        "coverage_state": "PARTIAL",
        "coverage_reason": "open_position_coverage_gap",
        "snapshot_row_count": 1,
        "expected_open_position_count": 2,
        "valued_position_count": 0,
        "unvalued_position_count": 1,
    }
    assert missing_snapshot_payload["total_market_value_reporting_currency"] is None
