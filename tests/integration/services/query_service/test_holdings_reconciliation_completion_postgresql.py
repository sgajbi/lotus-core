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
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

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
            PipelineStageState.epoch == 1,
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


async def _close_newer_source(session: AsyncSession, *, cash: bool = True) -> None:
    await _complete_control(session, seconds=30)
    for model in (PositionHistory, DailyPositionSnapshot):
        await session.execute(
            update(model)
            .where(model.portfolio_id == PORTFOLIO, model.security_id == SECURITIES[1])
            .values(
                quantity=Decimal("0"),
                cost_basis=Decimal("0"),
                cost_basis_local=Decimal("0"),
                updated_at=FACT_AT,
            )
        )
    await session.execute(
        update(DailyPositionSnapshot)
        .where(
            DailyPositionSnapshot.portfolio_id == PORTFOLIO,
            DailyPositionSnapshot.security_id == SECURITIES[1],
        )
        .values(
            market_price=Decimal("1"),
            market_value=Decimal("0"),
            market_value_local=Decimal("0"),
            updated_at=FACT_AT,
        )
    )
    await session.execute(
        update(Instrument)
        .where(Instrument.security_id == SECURITIES[1])
        .values(
            asset_class="CASH" if cash else "Equity",
            product_type="Cash" if cash else "Stock",
            updated_at=FACT_AT,
        )
    )
    session.add(
        PipelineStageState(
            stage_name="FINANCIAL_RECONCILIATION",
            transaction_id=f"{PORTFOLIO}_OLD_CONTROL",
            portfolio_id=PORTFOLIO,
            business_date=DAY,
            epoch=0,
            status="COMPLETED",
            created_at=FACT_AT - timedelta(seconds=10),
            updated_at=FACT_AT - timedelta(seconds=5),
        )
    )
    await session.commit()


@pytest.mark.parametrize("cash", [True, False])
@pytest.mark.parametrize("control_before_state", [True, False])
async def test_registered_holdings_retains_zero_cash_collective_epoch(
    holdings_client, cash: bool, control_before_state: bool
) -> None:
    """Cash and noncash closure must not select the old funding control for open equity."""
    client, session = holdings_client
    await _close_newer_source(session, cash=cash)
    foreign_id = f"{PORTFOLIO}_FOREIGN"
    session.add(
        Portfolio(
            portfolio_id=foreign_id,
            tenant_id="foreign-closed-cohort",
            base_currency="USD",
            open_date=DAY,
            risk_exposure="moderate",
            investment_time_horizon="long_term",
            portfolio_type="discretionary",
            booking_center_code="SG",
            client_id="FOREIGN_CLIENT",
            status="ACTIVE",
            created_at=FACT_AT,
            updated_at=FACT_AT,
        )
    )
    await session.flush()
    session.add(
        PositionState(
            portfolio_id=foreign_id,
            security_id=SECURITIES[0],
            epoch=9,
            status="CURRENT",
            watermark_date=DAY,
        )
    )
    await session.commit()
    if control_before_state:
        await _complete_control(session, seconds=10)
        await _complete_state(session, seconds=20)
    else:
        await _complete_state(session, seconds=20)
        await _complete_control(session, seconds=30)
    retained = await _durable_sources(session)
    response = await _read(client)
    assert [position["security_id"] for position in response["positions"]] == [SECURITIES[0]]
    assert response["reconciliation_status"] == response["data_quality_status"] == "COMPLETE"
    assert response["source_evidence_current"] is True
    assert response["degradation"]["reason_codes"] == []
    assert await _durable_sources(session) == retained
    await _complete_state(session, seconds=60)
    repeated = await _read(client)
    assert repeated["content_hash"] == response["content_hash"]
    foreign = await client.get(
        f"/portfolios/{PORTFOLIO}/positions",
        params={"as_of_date": DAY.isoformat()},
        headers={"X-Tenant-Id": "foreign-closed-cohort"},
    )
    assert foreign.status_code == 404

    original_override = app.dependency_overrides[get_async_db_session]
    factory = async_sessionmaker(session.bind, expire_on_commit=False)

    async def fresh_session():
        async with factory() as restarted:
            yield restarted

    app.dependency_overrides[get_async_db_session] = fresh_session
    try:
        restarted_response = await _read(client)
    finally:
        app.dependency_overrides[get_async_db_session] = original_override
    assert restarted_response["content_hash"] == repeated["content_hash"]


@pytest.mark.parametrize(
    "mutation,expected",
    [
        ("missing_history", "UNKNOWN"),
        ("missing_state", "UNKNOWN"),
        ("snapshot_only", "UNKNOWN"),
        ("missing_snapshot", "UNKNOWN"),
        ("state_epoch", "UNKNOWN"),
        ("snapshot_epoch", "UNKNOWN"),
        ("snapshot_quantity", "UNKNOWN"),
        ("unvalued", "UNKNOWN"),
        ("missing_value", "UNKNOWN"),
        ("currency", "UNKNOWN"),
        ("replaying", "UNKNOWN"),
        ("new_economics", "STALE"),
        ("missing_control", "UNRECONCILED"),
        ("failed_control", "BLOCKED"),
        ("stale_control", "STALE"),
    ],
)
async def test_registered_closed_cohort_fails_closed(holdings_client, mutation, expected):
    client, session = holdings_client
    await _close_newer_source(session)
    await session.execute(
        update(PipelineStageState)
        .where(
            PipelineStageState.portfolio_id == PORTFOLIO,
            PipelineStageState.epoch == 0,
        )
        .values(updated_at=FACT_AT + timedelta(seconds=30))
    )

    def predicates(model):
        return model.portfolio_id == PORTFOLIO, model.security_id == SECURITIES[1]

    if mutation in {"missing_state", "snapshot_only"}:
        await session.execute(delete(PositionState).where(*predicates(PositionState)))
        if mutation == "snapshot_only":
            await session.execute(delete(PositionHistory).where(*predicates(PositionHistory)))
    elif mutation in {"missing_history", "missing_snapshot"}:
        model = PositionHistory if mutation == "missing_history" else DailyPositionSnapshot
        await session.execute(delete(model).where(*predicates(model)))
    elif mutation in {"state_epoch", "replaying"}:
        values = {"epoch": 2} if mutation == "state_epoch" else {"status": "REPROCESSING"}
        await session.execute(
            update(PositionState).where(*predicates(PositionState)).values(**values)
        )
    elif mutation.endswith("control"):
        predicate = (PipelineStageState.portfolio_id == PORTFOLIO, PipelineStageState.epoch == 1)
        if mutation == "missing_control":
            await session.execute(delete(PipelineStageState).where(*predicate))
        else:
            values = (
                {"status": "FAILED"}
                if mutation == "failed_control"
                else {"updated_at": FACT_AT - timedelta(seconds=5)}
            )
            await session.execute(update(PipelineStageState).where(*predicate).values(**values))
    else:
        values = {
            "snapshot_epoch": {"epoch": 2},
            "snapshot_quantity": {"quantity": Decimal("1")},
            "unvalued": {"valuation_status": "PENDING"},
            "missing_value": {"market_value_local": None},
            "currency": {"valuation_source_currency": None, "valuation_reporting_currency": None},
            "new_economics": {"updated_at": FACT_AT + timedelta(seconds=40)},
        }[mutation]
        values.setdefault("updated_at", FACT_AT)
        await session.execute(
            update(DailyPositionSnapshot).where(*predicates(DailyPositionSnapshot)).values(**values)
        )
    await session.commit()
    retained = await _durable_sources(session)
    response = await _read(client)
    assert response["reconciliation_status"] == expected
    assert response["source_evidence_current"] is False
    assert await _durable_sources(session) == retained


@pytest.mark.parametrize("field", ["source", "reporting", "instrument", "portfolio"])
async def test_registered_closed_cohort_malformed_currency_fails_closed(holdings_client, field):
    client, session = holdings_client
    await _close_newer_source(session)
    await _complete_control(session, seconds=30)
    await session.execute(
        update(PipelineStageState)
        .where(PipelineStageState.portfolio_id == PORTFOLIO, PipelineStageState.epoch == 0)
        .values(updated_at=FACT_AT + timedelta(seconds=30))
    )
    if field in {"source", "reporting"}:
        column = f"valuation_{field}_currency"
        await session.execute(
            update(DailyPositionSnapshot)
            .where(
                DailyPositionSnapshot.portfolio_id == PORTFOLIO,
                DailyPositionSnapshot.security_id == SECURITIES[1],
            )
            .values(**{column: "US1", "updated_at": FACT_AT})
        )
    elif field == "instrument":
        await session.execute(
            update(Instrument)
            .where(Instrument.security_id == SECURITIES[1])
            .values(currency="US1", updated_at=FACT_AT)
        )
    else:
        await session.execute(
            update(Portfolio)
            .where(Portfolio.portfolio_id == PORTFOLIO)
            .values(base_currency="US1", updated_at=FACT_AT)
        )
    await session.commit()
    retained = await _durable_sources(session)
    response = await _read(client)
    assert [row["security_id"] for row in response["positions"]] == [SECURITIES[0]]
    assert response["reconciliation_status"] == "UNKNOWN"
    assert response["data_quality_status"] == "UNKNOWN"
    assert response["source_evidence_current"] is False
    assert "HOLDINGS_RECONCILIATION_UNKNOWN" in response["degradation"]["reason_codes"]
    assert await _durable_sources(session) == retained


@pytest.mark.parametrize("fully_closed", [False, True])
@pytest.mark.parametrize("missing_future_control", [False, True])
async def test_projected_cohort_retains_future_zero_authority(
    holdings_client, fully_closed, missing_future_control
):
    client, session = holdings_client
    await _close_newer_source(session, cash=False)
    future = DAY + timedelta(days=2000)
    for model, field in ((PositionHistory, "position_date"), (DailyPositionSnapshot, "date")):
        await session.execute(
            update(model)
            .where(model.portfolio_id == PORTFOLIO, model.security_id == SECURITIES[1])
            .values(**{field: future, "updated_at": FACT_AT + timedelta(seconds=10)})
        )
        if fully_closed:
            await session.execute(
                update(model)
                .where(model.portfolio_id == PORTFOLIO, model.security_id == SECURITIES[0])
                .values(quantity=Decimal("0"), updated_at=FACT_AT)
            )
    if fully_closed:
        for security, seconds in zip(SECURITIES, (0, 10), strict=True):
            await session.execute(
                update(DailyPositionSnapshot)
                .where(
                    DailyPositionSnapshot.portfolio_id == PORTFOLIO,
                    DailyPositionSnapshot.security_id == security,
                )
                .values(
                    market_value=Decimal("0"),
                    market_value_local=Decimal("0"),
                    updated_at=FACT_AT + timedelta(seconds=seconds),
                )
            )
    await session.execute(
        update(PositionState)
        .where(PositionState.portfolio_id == PORTFOLIO, PositionState.epoch == 1)
        .values(watermark_date=future)
    )
    await session.execute(
        update(PipelineStageState)
        .where(PipelineStageState.portfolio_id == PORTFOLIO)
        .values(updated_at=FACT_AT + timedelta(seconds=30))
    )
    future_control = (PipelineStageState.portfolio_id == PORTFOLIO, PipelineStageState.epoch == 1)
    if missing_future_control:
        await session.execute(delete(PipelineStageState).where(*future_control))
    else:
        await session.execute(
            update(PipelineStageState).where(*future_control).values(business_date=future)
        )
    session.add(
        PipelineStageState(
            stage_name="FINANCIAL_RECONCILIATION",
            transaction_id=f"{PORTFOLIO}_PROJECTED_CURRENT_DAY_CONTROL",
            portfolio_id=PORTFOLIO,
            business_date=DAY,
            epoch=1,
            status="COMPLETED",
            created_at=FACT_AT,
            updated_at=FACT_AT + timedelta(seconds=30),
        )
    )
    await session.commit()
    bounded = await client.get(
        f"/portfolios/{PORTFOLIO}/positions",
        params={"include_projected": "true", "as_of_date": DAY.isoformat()},
    )
    assert bounded.status_code == 200
    assert bounded.json()["reconciliation_status"] == "COMPLETE"
    retained = await _durable_sources(session)
    projected = await client.get(
        f"/portfolios/{PORTFOLIO}/positions", params={"include_projected": "true"}
    )
    assert projected.status_code == 200
    body = projected.json()
    assert body["as_of_date"] == (future if fully_closed else DAY).isoformat()
    assert body["reconciliation_status"] == (
        "UNRECONCILED" if missing_future_control else "COMPLETE"
    )
    assert body["source_evidence_current"] is (not missing_future_control)
    assert body["latest_evidence_timestamp"] == (
        FACT_AT + timedelta(seconds=10)
    ).isoformat().replace("+00:00", "Z")
    assert len(body["positions"]) == (0 if fully_closed else 1)
    assert await _durable_sources(session) == retained


async def test_portfolio_currency_correction_requires_fresh_reconciliation(holdings_client):
    client, session = holdings_client
    await _close_newer_source(session)
    await session.execute(
        update(PipelineStageState)
        .where(PipelineStageState.portfolio_id == PORTFOLIO)
        .values(updated_at=FACT_AT + timedelta(seconds=30))
    )
    await session.execute(
        update(Portfolio)
        .where(Portfolio.portfolio_id == PORTFOLIO)
        .values(base_currency="EUR", updated_at=FACT_AT)
    )
    await session.commit()
    invalid = await _read(client)
    assert invalid["reconciliation_status"] == "UNKNOWN"
    corrected_at = FACT_AT + timedelta(seconds=40)
    await session.execute(
        update(Portfolio)
        .where(Portfolio.portfolio_id == PORTFOLIO)
        .values(base_currency="USD", updated_at=corrected_at)
    )
    await session.commit()
    retained = await _durable_sources(session)
    corrected = await _read(client)
    assert corrected["reconciliation_status"] == "STALE"
    assert corrected["source_evidence_current"] is False
    assert corrected["latest_evidence_timestamp"] == corrected_at.isoformat().replace("+00:00", "Z")
    assert corrected["content_hash"] != invalid["content_hash"]
    assert await _durable_sources(session) == retained
    await session.execute(
        update(PipelineStageState)
        .where(PipelineStageState.portfolio_id == PORTFOLIO)
        .values(updated_at=FACT_AT + timedelta(seconds=50))
    )
    await session.commit()
    reconciled = await _read(client)
    assert reconciled["reconciliation_status"] == "COMPLETE"
    assert reconciled["source_evidence_current"] is True


async def test_registered_closed_cohort_uses_only_dated_snapshot_evidence(holdings_client):
    client, session = holdings_client
    await _close_newer_source(session)
    session.add(
        DailyPositionSnapshot(
            portfolio_id=PORTFOLIO,
            security_id=SECURITIES[1],
            date=DAY + timedelta(days=1),
            quantity=Decimal("0"),
            cost_basis=Decimal("0"),
            cost_basis_local=Decimal("0"),
            market_price=Decimal("1"),
            market_value=Decimal("0"),
            market_value_local=Decimal("0"),
            valuation_status="VALUED_CURRENT",
            valuation_source_currency="USD",
            valuation_reporting_currency="USD",
            epoch=1,
            created_at=FACT_AT + timedelta(seconds=40),
            updated_at=FACT_AT + timedelta(seconds=40),
        )
    )
    await session.commit()
    response = await _read(client)
    assert response["reconciliation_status"] == "COMPLETE"
    future = await client.get(
        f"/portfolios/{PORTFOLIO}/positions",
        params={"as_of_date": (DAY + timedelta(days=1)).isoformat()},
    )
    assert future.status_code == 200
    assert future.json()["reconciliation_status"] == "UNRECONCILED"


@pytest.mark.parametrize("missing_control", [False, True])
async def test_registered_fully_closed_cohort_is_observed_not_missing(
    holdings_client, missing_control
):
    client, session = holdings_client
    await _close_newer_source(session)
    for model in (PositionHistory, DailyPositionSnapshot):
        await session.execute(
            update(model)
            .where(
                model.portfolio_id == PORTFOLIO,
                model.security_id == SECURITIES[0],
            )
            .values(
                quantity=Decimal("0"),
                cost_basis=Decimal("0"),
                cost_basis_local=Decimal("0"),
                updated_at=FACT_AT,
            )
        )
    await session.execute(
        update(DailyPositionSnapshot)
        .where(
            DailyPositionSnapshot.portfolio_id == PORTFOLIO,
            DailyPositionSnapshot.security_id == SECURITIES[0],
        )
        .values(market_value=Decimal("0"), market_value_local=Decimal("0"), updated_at=FACT_AT)
    )
    if missing_control:
        await session.execute(
            delete(PipelineStageState).where(
                PipelineStageState.portfolio_id == PORTFOLIO,
                PipelineStageState.epoch == 1,
            )
        )
    await session.commit()
    response = await _read(client)
    assert response["positions"] == []
    assert response["reconciliation_status"] == ("UNRECONCILED" if missing_control else "COMPLETE")
    assert response["source_evidence_current"] is (not missing_control)
    assert "HOLDINGS_EMPTY" not in response["degradation"]["reason_codes"]


async def test_registered_zero_to_open_transition_preserves_prior_evidence(holdings_client):
    client, session = holdings_client
    await _close_newer_source(session, cash=False)
    for model in (PositionHistory, DailyPositionSnapshot):
        original = (
            await session.execute(
                select(model).where(
                    model.portfolio_id == PORTFOLIO,
                    model.security_id == SECURITIES[1],
                )
            )
        ).scalar_one()
        values = {
            column.name: getattr(original, column.name)
            for column in model.__table__.columns
            if column.name != "id"
        }
        values.update(
            epoch=2,
            quantity=Decimal("3"),
            cost_basis=Decimal("150"),
            cost_basis_local=Decimal("150"),
            created_at=FACT_AT + timedelta(seconds=40),
            updated_at=FACT_AT + timedelta(seconds=40),
        )
        if model is DailyPositionSnapshot:
            values.update(
                market_price=Decimal("50"),
                market_value=Decimal("150"),
                market_value_local=Decimal("150"),
            )
        session.add(model(**values))
    await session.execute(
        update(PositionState)
        .where(
            PositionState.portfolio_id == PORTFOLIO,
            PositionState.security_id == SECURITIES[1],
        )
        .values(epoch=2, updated_at=FACT_AT + timedelta(seconds=40))
    )
    session.add(
        PipelineStageState(
            stage_name="FINANCIAL_RECONCILIATION",
            transaction_id=f"{PORTFOLIO}_CONTROL_E2",
            portfolio_id=PORTFOLIO,
            business_date=DAY,
            epoch=2,
            status="COMPLETED",
            created_at=FACT_AT + timedelta(seconds=50),
            updated_at=FACT_AT + timedelta(seconds=50),
        )
    )
    await session.commit()
    response = await _read(client)
    assert response["reconciliation_status"] == "COMPLETE"
    assert response["source_evidence_current"] is True
    positions = {position["security_id"]: position for position in response["positions"]}
    assert Decimal(positions[SECURITIES[1]]["quantity"]) == Decimal("3")
    assert Decimal(positions[SECURITIES[1]]["valuation"]["market_value"]) == Decimal("150")
    retained_zero = (
        await session.execute(
            select(PositionHistory.quantity).where(
                PositionHistory.portfolio_id == PORTFOLIO,
                PositionHistory.security_id == SECURITIES[1],
                PositionHistory.epoch == 1,
            )
        )
    ).scalar_one()
    assert retained_zero == Decimal("0")


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
