"""Registered cash route/SQL proof; seeded controls are not live-worker certification."""

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import httpx
import pytest
import pytest_asyncio
from portfolio_common.database_models import (
    CashAccountMaster,
    DailyPositionSnapshot,
    Instrument,
    PipelineStageState,
    Portfolio,
    PositionHistory,
    PositionState,
    Transaction,
)
from portfolio_common.db import get_async_db_session
from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.services.query_service.app.main import app
from src.services.query_service.app.repositories.reporting_repository import ReportingRepository

pytestmark = [pytest.mark.asyncio, pytest.mark.db_direct]
DAY = date(2026, 12, 31)
AT = datetime(2026, 12, 31, 12, tzinfo=UTC)
PORTFOLIO = "CASH_ZERO_PROOF"
TENANT = "tenant-cash-zero-proof"
CASH = "CASH_ZERO_USD"
EQUITY = "CASH_ZERO_EQUITY"
CLOSED = "CASH_ZERO_CLOSED_EQUITY"


async def _seed(session: AsyncSession) -> None:
    session.add(
        Portfolio(
            tenant_id=TENANT,
            portfolio_id=PORTFOLIO,
            base_currency="USD",
            open_date=DAY,
            risk_exposure="moderate",
            investment_time_horizon="long_term",
            portfolio_type="discretionary",
            booking_center_code="SG",
            client_id="ZERO_CLIENT",
            status="ACTIVE",
            created_at=AT,
            updated_at=AT,
        )
    )
    await session.flush()
    for security, epoch, quantity, asset_class in (
        (CASH, 1, Decimal("0"), "CASH"),
        (EQUITY, 2, Decimal("10"), "Equity"),
        (CLOSED, 0, Decimal("0"), "Equity"),
    ):
        session.add(
            Instrument(
                security_id=security,
                name=security,
                currency="USD",
                isin=security,
                product_type="Cash" if asset_class == "CASH" else "Stock",
                asset_class=asset_class,
                created_at=AT,
                updated_at=AT,
            )
        )
        await session.flush()
        tx_id = f"{security}_TX"
        session.add(
            Transaction(
                transaction_id=tx_id,
                portfolio_id=PORTFOLIO,
                security_id=security,
                instrument_id=security,
                transaction_date=DAY,
                transaction_type="BUY",
                quantity=quantity,
                price=Decimal("10"),
                gross_transaction_amount=quantity * 10,
                trade_currency="USD",
                currency="USD",
            )
        )
        await session.flush()
        session.add(
            PositionState(
                portfolio_id=PORTFOLIO,
                security_id=security,
                epoch=epoch,
                status="CURRENT",
                watermark_date=DAY,
                created_at=AT,
                updated_at=AT,
            )
        )
        for fact_epoch, fact_quantity, fact_date in (
            [
                (0, Decimal("100"), DAY),
                (epoch, Decimal("100"), DAY - timedelta(days=1)),
                (epoch, quantity, DAY),
            ]
            if security == CASH
            else [(epoch, quantity, DAY)]
        ):
            value = fact_quantity if security == CASH else fact_quantity * 10
            session.add_all(
                [
                    PositionHistory(
                        portfolio_id=PORTFOLIO,
                        security_id=security,
                        transaction_id=tx_id,
                        position_date=fact_date,
                        quantity=fact_quantity,
                        cost_basis=value,
                        cost_basis_local=value,
                        epoch=fact_epoch,
                        created_at=AT,
                        updated_at=AT,
                    ),
                    DailyPositionSnapshot(
                        portfolio_id=PORTFOLIO,
                        security_id=security,
                        date=fact_date,
                        quantity=fact_quantity,
                        cost_basis=value,
                        cost_basis_local=value,
                        market_value=value,
                        market_value_local=value,
                        valuation_status="VALUED_CURRENT",
                        valuation_source_currency="USD",
                        valuation_reporting_currency="USD",
                        epoch=fact_epoch,
                        created_at=AT,
                        updated_at=AT,
                    ),
                ]
            )
    session.add_all(
        [
            CashAccountMaster(
                cash_account_id="ZERO_ACCOUNT",
                portfolio_id=PORTFOLIO,
                security_id=CASH,
                display_name="USD Cash",
                account_currency="USD",
                opened_on=DAY,
                created_at=AT,
                updated_at=AT,
            ),
            PipelineStageState(
                stage_name="FINANCIAL_RECONCILIATION",
                transaction_id=f"{PORTFOLIO}_CONTROL",
                portfolio_id=PORTFOLIO,
                business_date=DAY,
                epoch=2,
                status="COMPLETED",
                created_at=AT,
                updated_at=AT + timedelta(seconds=1),
            ),
        ]
    )
    await session.commit()


@pytest_asyncio.fixture
async def cash_client(clean_db, async_db_session: AsyncSession):
    await _seed(async_db_session)

    async def database_session():
        yield async_db_session

    assert get_async_db_session not in app.dependency_overrides
    app.dependency_overrides[get_async_db_session] = database_session
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://test",
            headers={"X-Tenant-Id": TENANT},
        ) as client:
            yield client, async_db_session
    finally:
        app.dependency_overrides.pop(get_async_db_session)
        await async_db_session.rollback()


async def _read(client):
    result = await client.get(
        f"/portfolios/{PORTFOLIO}/cash-balances",
        params={"as_of_date": DAY.isoformat()},
    )
    assert result.status_code == 200, result.text
    return result.json()


async def _retained(session):
    rows = []
    for model in (
        DailyPositionSnapshot,
        PositionHistory,
        PositionState,
        PipelineStageState,
        CashAccountMaster,
    ):
        result = await session.execute(
            select(model.__table__).where(model.portfolio_id == PORTFOLIO)
        )
        rows.extend(dict(row) for row in result.mappings())
    return rows


async def test_registered_cash_zero_uses_current_epoch_and_collective_control_without_writes(
    cash_client,
):
    client, session = cash_client
    repo = ReportingRepository(session)
    ordinary = await repo.list_latest_snapshot_rows(portfolio_ids=[PORTFOLIO], as_of_date=DAY)
    assert [row.snapshot.security_id for row in ordinary] == [EQUITY]
    assert await repo.count_latest_open_position_keys(portfolio_id=PORTFOLIO, as_of_date=DAY) == 1
    retained = await _retained(session)
    first = await _read(client)
    assert first["data_quality_status"] == first["reconciliation_status"] == "COMPLETE"
    assert first["source_evidence_current"] is True
    assert len(first["cash_accounts"]) == 1
    assert Decimal(first["cash_accounts"][0]["balance_portfolio_currency"]) == 0
    assert Decimal(first["totals"]["source_reported_cash_weight"]) == 0
    assert (
        Decimal(first["totals"]["source_reported_cash_weight_denominator_portfolio_currency"])
        == 100
    )
    assert (await _read(client))["snapshot_id"] == first["snapshot_id"]
    assert await _retained(session) == retained
    await session.execute(
        update(PositionState)
        .where(
            PositionState.portfolio_id == PORTFOLIO,
        )
        .values(updated_at=AT + timedelta(days=1))
    )
    await session.commit()
    assert (await _read(client))["snapshot_id"] == first["snapshot_id"]
    hidden = await client.get(
        f"/portfolios/{PORTFOLIO}/cash-balances",
        params={"as_of_date": DAY.isoformat()},
        headers={"X-Tenant-Id": "different-tenant"},
    )
    assert hidden.status_code == 404


@pytest.mark.parametrize(
    "mutation",
    [
        "missing_control",
        "adverse_control",
        "wrong_day",
        "wrong_epoch",
        "pending",
        "failed",
        "requires_replay",
        "old_control",
        "unvalued",
        "null_value",
        "null_local",
        "missing_currency",
        "old_cash_date",
        "state_replay",
        "state_epoch_mismatch",
        "missing_equity",
        "missing_cash",
        "mixed_master_only",
    ],
)
async def test_registered_cash_zero_refuses_unqualified_source(cash_client, mutation):
    client, session = cash_client
    before = await _read(client)
    if mutation == "missing_control":
        await session.execute(delete(PipelineStageState))
    elif mutation == "adverse_control":
        session.add(
            PipelineStageState(
                stage_name="FINANCIAL_RECONCILIATION",
                transaction_id="ADVERSE_CONTROL",
                portfolio_id=PORTFOLIO,
                business_date=DAY,
                epoch=2,
                status="FAILED",
                created_at=AT,
                updated_at=AT + timedelta(seconds=1),
            )
        )
    elif mutation in {
        "wrong_day",
        "wrong_epoch",
        "pending",
        "failed",
        "requires_replay",
        "old_control",
    }:
        changes = {
            "wrong_day": {"business_date": DAY - timedelta(days=1)},
            "wrong_epoch": {"epoch": 1},
            "pending": {"status": "PENDING"},
            "failed": {"status": "FAILED"},
            "requires_replay": {"status": "REQUIRES_REPLAY"},
            "old_control": {"updated_at": AT - timedelta(seconds=1)},
        }[mutation]
        await session.execute(update(PipelineStageState).values(**changes))
    elif mutation in {"state_replay", "state_epoch_mismatch"}:
        await session.execute(
            update(PositionState)
            .where(PositionState.security_id == CASH)
            .values(**({"status": "REPLAYING"} if mutation == "state_replay" else {"epoch": 3}))
        )
    elif mutation == "mixed_master_only":
        session.add(
            CashAccountMaster(
                cash_account_id="MISSING_ACCOUNT",
                portfolio_id=PORTFOLIO,
                security_id="MISSING_CASH",
                display_name="Unobserved Cash",
                account_currency="USD",
                opened_on=DAY,
            )
        )
    elif mutation in {"missing_cash", "missing_equity"}:
        await session.execute(
            delete(DailyPositionSnapshot).where(
                DailyPositionSnapshot.security_id
                == (CASH if mutation == "missing_cash" else EQUITY)
            )
        )
    else:
        changes = {
            "unvalued": {"valuation_status": "UNVALUED"},
            "null_value": {"market_value": None},
            "null_local": {"market_value_local": None},
            "missing_currency": {
                "valuation_source_currency": None,
                "valuation_reporting_currency": None,
            },
            "old_cash_date": {"date": DAY - timedelta(days=2)},
        }[mutation]
        await session.execute(
            update(DailyPositionSnapshot)
            .where(
                DailyPositionSnapshot.security_id == CASH,
                DailyPositionSnapshot.epoch == 1,
                DailyPositionSnapshot.date == DAY,
            )
            .values(**changes)
        )
    await session.commit()
    retained = await _retained(session)
    result = await _read(client)
    assert result["data_quality_status"] != "COMPLETE"
    assert result["source_evidence_current"] is False
    assert result["snapshot_id"] != before["snapshot_id"]
    assert await _retained(session) == retained
    if mutation == "missing_equity":
        assert (
            result["totals"]["source_reported_cash_weight_supportability"]
            == "BLOCKED_MISSING_DENOMINATOR"
        )
    if mutation in {"state_epoch_mismatch", "missing_cash"}:
        assert Decimal(result["cash_accounts"][0]["balance_portfolio_currency"]) == 0


async def test_same_zero_at_new_epoch_changes_registered_source_identity(cash_client):
    client, session = cash_client
    before = await _read(client)
    for model in (PositionState, PositionHistory, DailyPositionSnapshot):
        await session.execute(
            update(model)
            .where(
                model.security_id == CASH,
                model.epoch == 1,
            )
            .values(epoch=3)
        )
    await session.execute(
        update(PipelineStageState).values(epoch=3, updated_at=AT + timedelta(seconds=2))
    )
    await session.commit()
    after = await _read(client)
    assert after["source_evidence_current"] is True
    assert after["snapshot_id"] != before["snapshot_id"]
    assert after["totals"] == before["totals"]


@pytest.mark.parametrize("cash_quantity", [Decimal("0"), Decimal("25")])
async def test_registered_cash_fact_without_open_equity_keeps_balance_qualification(
    cash_client, cash_quantity
):
    client, session = cash_client
    for model in (PositionHistory, DailyPositionSnapshot):
        await session.execute(
            update(model).where(model.security_id == EQUITY).values(quantity=Decimal("0"))
        )
        values = {"quantity": cash_quantity}
        if model is DailyPositionSnapshot:
            values.update(market_value=cash_quantity, market_value_local=cash_quantity)
        await session.execute(
            update(model).where(model.security_id == CASH, model.epoch == 1).values(**values)
        )
    await session.execute(
        update(PipelineStageState).values(epoch=1, updated_at=AT + timedelta(seconds=2))
    )
    await session.commit()
    result = await _read(client)
    assert result["data_quality_status"] == "COMPLETE"
    assert result["source_evidence_current"] is True
    assert Decimal(result["totals"]["total_balance_portfolio_currency"]) == cash_quantity
    assert result["totals"]["source_reported_cash_weight_supportability"] == (
        "BLOCKED_ZERO_DENOMINATOR" if cash_quantity == 0 else "SUPPORTED"
    )
