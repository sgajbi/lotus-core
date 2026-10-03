"""Registered query/SQL proof; seeded controls do not substitute for live-worker proof."""

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import httpx
import pytest
import pytest_asyncio
from portfolio_common.database_models import (
    DailyPositionSnapshot,
    Instrument,
    MarketPrice,
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

pytestmark = [pytest.mark.asyncio, pytest.mark.db_direct]

DAY = date(2026, 4, 10)
FACT_AT = datetime(2026, 4, 10, 12, tzinfo=UTC)
TENANT = "tenant-holdings-completion-proof"
PORTFOLIO = "HOLDINGS_COMPLETION_PROOF"
SECURITIES = ("HOLDINGS_COMPLETION_E0", "HOLDINGS_COMPLETION_E1")


async def _seed_sources(session: AsyncSession) -> None:
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
            client_id="HC_CLIENT",
            status="ACTIVE",
            created_at=FACT_AT,
            updated_at=FACT_AT,
        )
    )
    await session.flush()
    for epoch, security in enumerate(SECURITIES):
        quantity = Decimal(epoch + 1)
        price = Decimal("100") / quantity
        transaction_id = f"{PORTFOLIO}_BUY_{epoch}"
        session.add(
            Instrument(
                security_id=security,
                name=f"Completion equity {epoch}",
                currency="USD",
                isin=f"XS000115700{epoch}",
                product_type="Stock",
                asset_class="Equity",
                created_at=FACT_AT,
                updated_at=FACT_AT,
            )
        )
        await session.flush()
        session.add(
            Transaction(
                transaction_id=transaction_id,
                portfolio_id=PORTFOLIO,
                security_id=security,
                instrument_id=security,
                transaction_date=DAY,
                transaction_type="BUY",
                quantity=quantity,
                price=price,
                gross_transaction_amount=Decimal("100"),
                trade_currency="USD",
                currency="USD",
            )
        )
        await session.flush()
        session.add_all(
            [
                PositionHistory(
                    portfolio_id=PORTFOLIO,
                    security_id=security,
                    transaction_id=transaction_id,
                    position_date=DAY,
                    quantity=quantity,
                    cost_basis=Decimal("100"),
                    cost_basis_local=Decimal("100"),
                    epoch=epoch,
                    created_at=FACT_AT,
                    updated_at=FACT_AT,
                ),
                PositionState(
                    portfolio_id=PORTFOLIO,
                    security_id=security,
                    epoch=epoch,
                    status="CURRENT",
                    watermark_date=DAY,
                    created_at=FACT_AT,
                    updated_at=FACT_AT,
                ),
                DailyPositionSnapshot(
                    portfolio_id=PORTFOLIO,
                    security_id=security,
                    date=DAY,
                    quantity=quantity,
                    cost_basis=Decimal("100"),
                    cost_basis_local=Decimal("100"),
                    market_price=price,
                    market_value=Decimal("100"),
                    market_value_local=Decimal("100"),
                    unrealized_gain_loss=Decimal("0"),
                    unrealized_gain_loss_local=Decimal("0"),
                    valuation_status="VALUED_CURRENT",
                    valuation_source_currency="USD",
                    valuation_reporting_currency="USD",
                    epoch=epoch,
                    created_at=FACT_AT,
                    updated_at=FACT_AT,
                ),
                MarketPrice(
                    security_id=security,
                    price_date=DAY,
                    price=price,
                    currency="USD",
                ),
            ]
        )
    session.add(
        PipelineStageState(
            stage_name="FINANCIAL_RECONCILIATION",
            transaction_id=f"{PORTFOLIO}_CONTROL",
            portfolio_id=PORTFOLIO,
            business_date=DAY,
            epoch=1,
            status="PENDING",
            created_at=FACT_AT,
            updated_at=FACT_AT,
        )
    )
    await session.commit()


async def _complete_control(session: AsyncSession, *, seconds: int) -> None:
    await session.execute(
        update(PipelineStageState)
        .where(
            PipelineStageState.portfolio_id == PORTFOLIO,
        )
        .values(status="COMPLETED", updated_at=FACT_AT + timedelta(seconds=seconds))
    )
    await session.commit()


async def _complete_state(session: AsyncSession, *, seconds: int) -> None:
    await session.execute(
        update(PositionState)
        .where(
            PositionState.portfolio_id == PORTFOLIO,
        )
        .values(status="CURRENT", updated_at=FACT_AT + timedelta(seconds=seconds))
    )
    await session.commit()


async def _durable_sources(session: AsyncSession) -> list[dict[str, object]]:
    """Compare complete retained rows so GET side-effect refusal is not inferred."""
    rows: list[dict[str, object]] = []
    for model in (DailyPositionSnapshot, PositionHistory, PositionState, PipelineStageState):
        result = await session.execute(
            select(model.__table__).where(model.portfolio_id == PORTFOLIO)
        )
        rows.extend(dict(row) for row in result.mappings())
    return rows


@pytest_asyncio.fixture
async def holdings_client(clean_db, async_db_session: AsyncSession):
    await _seed_sources(async_db_session)

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


async def _read(client: httpx.AsyncClient) -> dict[str, object]:
    response = await client.get(
        f"/portfolios/{PORTFOLIO}/positions", params={"as_of_date": DAY.isoformat()}
    )
    assert response.status_code == 200, response.text
    return response.json()


@pytest.mark.parametrize("control_before_state", [True, False])
async def test_registered_holdings_keeps_both_completion_orders_current(
    holdings_client, control_before_state: bool
) -> None:
    client, session = holdings_client
    if control_before_state:
        await _complete_control(session, seconds=10)
        await _complete_state(session, seconds=20)
    else:
        await _complete_state(session, seconds=20)
        await _complete_control(session, seconds=30)
    retained = await _durable_sources(session)
    first = await _read(client)
    assert first["reconciliation_status"] == first["data_quality_status"] == "COMPLETE"
    assert first["freshness_status"] == "CURRENT"
    assert first["source_evidence_current"] is True
    assert first["degradation"]["reason_codes"] == []
    assert first["source_digest"] == first["content_hash"]
    positions = {p["security_id"]: p for p in first["positions"]}
    assert set(positions) == set(SECURITIES)
    for epoch, security in enumerate(SECURITIES):
        position = positions[security]
        assert Decimal(position["quantity"]) == Decimal(epoch + 1)
        assert Decimal(position["cost_basis"]) == Decimal("100")
        assert Decimal(position["valuation"]["market_value"]) == Decimal("100")
        assert Decimal(position["valuation"]["unrealized_gain_loss"]) == Decimal("0")
        assert position["reprocessing_status"] == "CURRENT"
    assert await _durable_sources(session) == retained

    await _complete_state(session, seconds=60)
    late_retained = await _durable_sources(session)
    repeat = await _read(client)
    for field in (
        "content_hash",
        "source_digest",
        "snapshot_id",
        "source_refs",
        "source_lineage",
        "positions",
        "degradation",
    ):
        assert repeat[field] == first[field], field
    assert repeat["source_evidence_current"] is True
    assert await _durable_sources(session) == late_retained
    # Tenant admission remains non-disclosing, including a real owned portfolio ID.
    foreign = await client.get(
        f"/portfolios/{PORTFOLIO}/positions",
        headers={"X-Tenant-Id": "tenant-foreign"},
        params={"as_of_date": DAY.isoformat()},
    )
    absent = await client.get(
        "/portfolios/HC_ABSENT/positions", params={"as_of_date": DAY.isoformat()}
    )
    assert foreign.status_code == absent.status_code == 404


@pytest.mark.parametrize(
    "mutation,status,reason",
    [
        ("missing", "UNRECONCILED", "HOLDINGS_RECONCILIATION_CONTROL_MISSING"),
        ("wrong_epoch", "UNRECONCILED", "HOLDINGS_RECONCILIATION_CONTROL_MISSING"),
        ("pending", "PARTIAL", "HOLDINGS_RECONCILIATION_INCOMPLETE"),
        ("failed", "BLOCKED", "HOLDINGS_RECONCILIATION_BLOCKED"),
        ("replay_control", "BLOCKED", "HOLDINGS_RECONCILIATION_BLOCKED"),
        ("unknown", "UNKNOWN", "HOLDINGS_RECONCILIATION_UNKNOWN"),
        ("new_snapshot", "STALE", "HOLDINGS_RECONCILIATION_EVIDENCE_NEWER_THAN_CONTROL"),
        ("new_reference", "STALE", "HOLDINGS_RECONCILIATION_EVIDENCE_NEWER_THAN_CONTROL"),
        ("state_replay", "COMPLETE", "POSITION_STATE_NOT_CURRENT"),
        ("missing_price", "COMPLETE", "MARKET_PRICE_EVIDENCE_MISSING"),
        ("missing_currency", "COMPLETE", "VALUATION_CURRENCY_LINEAGE_MISSING"),
    ],
)
async def test_registered_holdings_preserves_real_source_and_control_refusals(
    holdings_client, mutation: str, status: str, reason: str
) -> None:
    client, session = holdings_client
    await _complete_control(session, seconds=10)
    await _complete_state(session, seconds=20)
    predicate = PipelineStageState.portfolio_id == PORTFOLIO
    if mutation == "missing":
        await session.execute(delete(PipelineStageState).where(predicate))
    elif mutation == "wrong_epoch":
        await session.execute(update(PipelineStageState).where(predicate).values(epoch=2))
    elif mutation in {"pending", "failed", "replay_control", "unknown"}:
        value = {
            "pending": "PENDING",
            "failed": "FAILED",
            "replay_control": "REQUIRES_REPLAY",
            "unknown": "legacy",
        }[mutation]
        await session.execute(update(PipelineStageState).where(predicate).values(status=value))
    elif mutation == "new_snapshot":
        await session.execute(
            update(DailyPositionSnapshot)
            .where(DailyPositionSnapshot.portfolio_id == PORTFOLIO)
            .values(updated_at=FACT_AT + timedelta(seconds=40))
        )
    elif mutation == "new_reference":
        await session.execute(
            update(Instrument)
            .where(Instrument.security_id.in_(SECURITIES))
            .values(updated_at=FACT_AT + timedelta(seconds=40))
        )
    elif mutation == "state_replay":
        await session.execute(
            update(PositionState)
            .where(PositionState.portfolio_id == PORTFOLIO)
            .values(status="REPROCESSING")
        )
    elif mutation == "missing_price":
        await session.execute(delete(MarketPrice).where(MarketPrice.security_id.in_(SECURITIES)))
    else:
        assert mutation == "missing_currency"
        await session.execute(
            update(DailyPositionSnapshot)
            .where(DailyPositionSnapshot.portfolio_id == PORTFOLIO)
            .values(
                valuation_source_currency=None,
                valuation_reporting_currency=None,
                updated_at=FACT_AT,
            )
        )
    await session.commit()
    retained = await _durable_sources(session)
    response = await _read(client)
    assert response["reconciliation_status"] == status
    assert response["source_evidence_current"] is False
    assert response["freshness_status"] != "CURRENT"
    assert reason in response["degradation"]["reason_codes"]
    assert await _durable_sources(session) == retained
