"""Prove collective source epoch semantics through production QCP and PostgreSQL."""

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import httpx
import pytest
from portfolio_common.database_models import (
    DailyPositionSnapshot,
    Instrument,
    PipelineStageState,
    Portfolio,
    PositionHistory,
    PositionState,
    Transaction,
)
from portfolio_common.db import get_async_db_session
from portfolio_common.reconciliation_quality import FINANCIAL_RECONCILIATION_STAGE
from sqlalchemy import delete, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.services.query_control_plane_service.app.main import app

pytestmark = [pytest.mark.asyncio, pytest.mark.db_direct, pytest.mark.lifecycle]

DAY = date(2026, 4, 10)
FACT_TIME = datetime(2026, 4, 10, 1, tzinfo=UTC)
CONTROL_TIME = FACT_TIME + timedelta(minutes=5)
VALUATION_TIME = CONTROL_TIME + timedelta(minutes=5)
TENANT = "tenant-core-collective-epoch"
PORTFOLIO = "CORE_COLLECTIVE_EPOCH_PROOF"


async def _seed_collective_sources(session: AsyncSession, *, carry_forward: bool) -> None:
    session.add(
        Portfolio(
            tenant_id=TENANT,
            portfolio_id=PORTFOLIO,
            base_currency="USD",
            open_date=date(2026, 1, 1),
            risk_exposure="moderate",
            investment_time_horizon="long_term",
            portfolio_type="discretionary",
            booking_center_code="SG",
            client_id="CLIENT_CORE_COLLECTIVE_EPOCH",
            status="ACTIVE",
            created_at=FACT_TIME,
            updated_at=FACT_TIME,
        )
    )
    for epoch, quantity, price in [
        (0, Decimal("1"), Decimal("10")),
        (1, Decimal("2"), Decimal("20")),
    ]:
        security = f"CORE_COLLECTIVE_S{epoch}"
        transaction = f"CORE-COLLECTIVE-T{epoch}"
        financial_day = DAY - timedelta(days=1) if carry_forward and epoch == 0 else DAY
        session.add(
            Instrument(
                security_id=security,
                name=f"Collective Epoch Equity {epoch}",
                isin=f"XS00000010{epoch}5",
                currency="USD",
                product_type="Stock",
                asset_class="Equity",
                sector="Financials",
                country_of_risk="SG",
            )
        )
        await session.flush()
        session.add(
            Transaction(
                transaction_id=transaction,
                portfolio_id=PORTFOLIO,
                security_id=security,
                instrument_id=security,
                transaction_date=financial_day,
                transaction_type="BUY",
                quantity=quantity,
                price=price,
                gross_transaction_amount=quantity * price,
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
                    transaction_id=transaction,
                    position_date=financial_day,
                    quantity=quantity,
                    cost_basis=quantity * price,
                    cost_basis_local=quantity * price,
                    epoch=epoch,
                    created_at=FACT_TIME,
                    updated_at=FACT_TIME,
                ),
                PositionState(
                    portfolio_id=PORTFOLIO,
                    security_id=security,
                    epoch=epoch,
                    watermark_date=DAY,
                    status="CURRENT",
                    created_at=FACT_TIME,
                    updated_at=VALUATION_TIME,
                ),
                DailyPositionSnapshot(
                    portfolio_id=PORTFOLIO,
                    security_id=security,
                    date=DAY,
                    quantity=quantity,
                    cost_basis=quantity * price,
                    cost_basis_local=quantity * price,
                    market_price=price,
                    market_value=quantity * price,
                    market_value_local=quantity * price,
                    valuation_status="VALUED_CURRENT",
                    valuation_source_currency="USD",
                    valuation_reporting_currency="USD",
                    epoch=epoch,
                    created_at=VALUATION_TIME,
                    updated_at=VALUATION_TIME,
                ),
            ]
        )
    session.add(
        PipelineStageState(
            stage_name=FINANCIAL_RECONCILIATION_STAGE,
            transaction_id=f"reconciliation:{PORTFOLIO}:{DAY}",
            portfolio_id=PORTFOLIO,
            business_date=DAY,
            epoch=1,
            status="COMPLETED",
            created_at=CONTROL_TIME,
            updated_at=CONTROL_TIME,
        )
    )
    if carry_forward:
        session.add(
            PipelineStageState(
                stage_name=FINANCIAL_RECONCILIATION_STAGE,
                transaction_id=f"reconciliation:{PORTFOLIO}:{DAY - timedelta(days=1)}",
                portfolio_id=PORTFOLIO,
                business_date=DAY - timedelta(days=1),
                epoch=1,
                status="COMPLETED",
                created_at=CONTROL_TIME,
                updated_at=CONTROL_TIME,
            )
        )
    await session.commit()


async def _mutate_source_evidence(session: AsyncSession, *, mutation: str) -> None:
    if mutation == "missing_control":
        await session.execute(
            delete(PipelineStageState).where(PipelineStageState.portfolio_id == PORTFOLIO)
        )
    elif mutation == "wrong_control_epoch":
        await session.execute(
            update(PipelineStageState)
            .where(PipelineStageState.portfolio_id == PORTFOLIO)
            .values(epoch=0)
        )
    elif mutation == "pending_control":
        await session.execute(
            update(PipelineStageState)
            .where(PipelineStageState.portfolio_id == PORTFOLIO)
            .values(status="PENDING")
        )
    elif mutation == "failed_control":
        await session.execute(
            update(PipelineStageState)
            .where(PipelineStageState.portfolio_id == PORTFOLIO)
            .values(status="FAILED")
        )
    elif mutation == "stale_control":
        await session.execute(
            update(PipelineStageState)
            .where(PipelineStageState.portfolio_id == PORTFOLIO)
            .values(updated_at=FACT_TIME - timedelta(minutes=1))
        )
    elif mutation == "state_epoch_mismatch":
        await session.execute(
            update(PositionState)
            .where(
                PositionState.portfolio_id == PORTFOLIO,
                PositionState.security_id == "CORE_COLLECTIVE_S1",
            )
            .values(epoch=2)
        )
    elif mutation == "state_reprocessing":
        await session.execute(
            update(PositionState)
            .where(
                PositionState.portfolio_id == PORTFOLIO,
                PositionState.security_id == "CORE_COLLECTIVE_S1",
            )
            .values(status="REPROCESSING")
        )
    elif mutation == "missing_valuation":
        await session.execute(
            delete(DailyPositionSnapshot).where(
                DailyPositionSnapshot.portfolio_id == PORTFOLIO,
                DailyPositionSnapshot.security_id == "CORE_COLLECTIVE_S1",
            )
        )
    await session.commit()


@pytest.mark.parametrize(
    "mutation,expected_reconciliation",
    [
        ("valid", "COMPLETE"),
        ("carry_forward", "COMPLETE"),
        ("missing_control", "UNRECONCILED"),
        ("wrong_control_epoch", "UNRECONCILED"),
        ("pending_control", "PARTIAL"),
        ("failed_control", "BLOCKED"),
        ("stale_control", "STALE"),
        ("state_epoch_mismatch", "UNKNOWN"),
        ("state_reprocessing", "COMPLETE"),
        ("missing_valuation", "COMPLETE"),
    ],
)
async def test_core_snapshot_collective_target_preserves_source_currentness(
    clean_db, async_db_session: AsyncSession, mutation: str, expected_reconciliation: str
) -> None:
    await _seed_collective_sources(async_db_session, carry_forward=mutation == "carry_forward")
    await _mutate_source_evidence(async_db_session, mutation=mutation)

    async def database_session():
        yield async_db_session

    assert get_async_db_session not in app.dependency_overrides
    app.dependency_overrides[get_async_db_session] = database_session
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.post(
                f"/integration/portfolios/{PORTFOLIO}/core-snapshot",
                headers={"X-Tenant-Id": TENANT},
                json={
                    "tenant_id": TENANT,
                    "consumer_system": "lotus-advise",
                    "as_of_date": DAY.isoformat(),
                    "snapshot_mode": "BASELINE",
                    "reporting_currency": "USD",
                    "sections": ["portfolio_state", "portfolio_totals"],
                },
            )
            if mutation in {"valid", "carry_forward"}:
                repeated = await client.post(
                    f"/integration/portfolios/{PORTFOLIO}/core-snapshot",
                    headers={"X-Tenant-Id": TENANT, "Content-Type": "application/json"},
                    content=response.request.content,
                )
                assert repeated.status_code == 200, repeated.text
                for field in (
                    "content_hash",
                    "snapshot_id",
                    "request_fingerprint",
                    "calculation_lineage",
                ):
                    assert repeated.json()[field] == response.json()[field]
        assert response.status_code == 200, response.text
        payload = response.json()
        assert payload["reconciliation_status"] == expected_reconciliation, payload
        positions = payload["sections"]["portfolio_state"]
        assert len(positions) == 2
        assert Decimal(
            payload["sections"]["portfolio_totals"]["baseline_total_market_value_base"]
        ) == Decimal("50")
        assert {
            row["security_id"]: (
                Decimal(row["quantity"]),
                Decimal(row["market_value_base"]),
                Decimal(row["weight"]),
            )
            for row in positions
        } == {
            "CORE_COLLECTIVE_S0": (Decimal("1"), Decimal("10"), Decimal("0.2")),
            "CORE_COLLECTIVE_S1": (Decimal("2"), Decimal("40"), Decimal("0.8")),
        }
        if mutation in {"valid", "carry_forward"}:
            assert payload["source_evidence_current"] is True
            assert payload["valuation_context"]["supportability"] == "READY"
            assert payload["freshness"]["snapshot_epoch"] == 1, payload
            assert payload["data_quality_status"] == "COMPLETE", payload
        else:
            assert payload["source_evidence_current"] is False
            if mutation != "state_reprocessing":
                assert payload["data_quality_status"] != "COMPLETE", payload
        if mutation in {"state_epoch_mismatch", "missing_valuation"}:
            assert payload["freshness"]["snapshot_epoch"] is None
        if mutation in {"state_reprocessing", "missing_valuation"}:
            assert payload["valuation_context"]["supportability"] == "UNAVAILABLE"
    finally:
        app.dependency_overrides.pop(get_async_db_session)
