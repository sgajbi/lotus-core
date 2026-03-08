from datetime import date, datetime, timezone
from decimal import Decimal

import httpx
import pytest
import pytest_asyncio
from portfolio_common.database_models import (
    CashflowRule,
    DailyPositionSnapshot,
    FinancialReconciliationFinding,
    FinancialReconciliationRun,
    Instrument,
    Portfolio,
    PortfolioTimeseries,
    PositionTimeseries,
    Transaction,
)
from portfolio_common.db import get_async_db_session
from sqlalchemy.ext.asyncio import AsyncSession

from src.services.financial_reconciliation_service.app.main import app, lifespan

pytestmark = pytest.mark.asyncio


@pytest_asyncio.fixture
async def async_test_client(async_db_session: AsyncSession):
    async def override_db():
        yield async_db_session

    app.dependency_overrides[get_async_db_session] = override_db
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield client
    app.dependency_overrides.pop(get_async_db_session, None)


@pytest_asyncio.fixture
async def ensure_reconciliation_tables(async_db_session: AsyncSession):
    async with async_db_session.bind.begin() as connection:
        await connection.run_sync(
            FinancialReconciliationRun.__table__.create,
            checkfirst=True,
        )
        await connection.run_sync(
            FinancialReconciliationFinding.__table__.create,
            checkfirst=True,
        )
    yield


async def _seed_portfolio(async_db_session: AsyncSession, portfolio_id: str) -> None:
    async_db_session.add(
        Portfolio(
            portfolio_id=portfolio_id,
            base_currency="USD",
            open_date=date(2020, 1, 1),
            risk_exposure="MEDIUM",
            investment_time_horizon="LONG",
            portfolio_type="DISCRETIONARY",
            booking_center_code="SG",
            client_id=f"CLIENT-{portfolio_id}",
            status="ACTIVE",
        )
    )
    await async_db_session.commit()


async def _seed_instrument(async_db_session: AsyncSession, security_id: str) -> None:
    async_db_session.add(
        Instrument(
            security_id=security_id,
            name=f"Instrument {security_id}",
            isin=f"ISIN{security_id:0>8}"[-12:],
            currency="USD",
            product_type="EQUITY",
        )
    )
    await async_db_session.commit()


async def test_lifespan_logs_startup_and_shutdown():
    from unittest.mock import patch

    with patch("src.services.financial_reconciliation_service.app.main.logger.info") as logger_info:
        async with lifespan(app):
            pass

    logged_messages = [args[0] for args, _ in logger_info.call_args_list]
    assert "Financial Reconciliation Service starting up..." in logged_messages
    assert any("shutting down" in message for message in logged_messages)
    assert "Financial Reconciliation Service has shut down gracefully." in logged_messages


async def test_openapi_contains_reconciliation_endpoints(async_test_client: httpx.AsyncClient):
    response = await async_test_client.get("/openapi.json")
    assert response.status_code == 200
    paths = response.json()["paths"]
    assert "/reconciliation/runs/transaction-cashflow" in paths
    assert "/reconciliation/runs/position-valuation" in paths
    assert "/reconciliation/runs/timeseries-integrity" in paths
    assert "/reconciliation/runs/{run_id}/findings" in paths


async def test_openapi_includes_reconciliation_examples(async_test_client: httpx.AsyncClient):
    response = await async_test_client.get("/openapi.json")
    assert response.status_code == 200
    schema = response.json()

    post_operation = schema["paths"]["/reconciliation/runs/transaction-cashflow"]["post"]
    request_examples = post_operation["requestBody"]["content"]["application/json"]["examples"]
    response_example = post_operation["responses"]["200"]["content"]["application/json"]["example"]

    assert "portfolio_day_scope" in request_examples
    assert request_examples["portfolio_day_scope"]["value"]["portfolio_id"] == "PORT-OPS-001"
    assert response_example["run_id"] == "FRR-20260306-0001"

    finding_example = (
        schema["paths"]["/reconciliation/runs/{run_id}/findings"]["get"]["responses"]["200"][
            "content"
        ]["application/json"]["example"]
    )
    assert finding_example["findings"][0]["finding_type"] == "missing_cashflow"


async def test_transaction_cashflow_run_persists_missing_cashflow_finding(
    async_test_client: httpx.AsyncClient,
    async_db_session: AsyncSession,
    clean_db,
    ensure_reconciliation_tables,
):
    await _seed_portfolio(async_db_session, "PORT-R1")
    async_db_session.add(
        CashflowRule(
            transaction_type="RECON_BUY",
            classification="EXTERNAL",
            timing="SETTLEMENT",
            is_position_flow=True,
            is_portfolio_flow=False,
        )
    )
    async_db_session.add(
        Transaction(
            transaction_id="TXN-R1",
            portfolio_id="PORT-R1",
            instrument_id="INST-1",
            security_id="SEC-R1",
            transaction_type="RECON_BUY",
            quantity=Decimal("10"),
            price=Decimal("11"),
            gross_transaction_amount=Decimal("110"),
            trade_currency="USD",
            currency="USD",
            transaction_date=datetime(2026, 3, 8, tzinfo=timezone.utc),
            settlement_date=datetime(2026, 3, 10, tzinfo=timezone.utc),
        )
    )
    await async_db_session.commit()

    response = await async_test_client.post(
        "/reconciliation/runs/transaction-cashflow",
        json={"portfolio_id": "PORT-R1", "business_date": "2026-03-08", "requested_by": "qa"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["summary"]["finding_count"] == 1
    assert payload["summary"]["passed"] is False

    findings_response = await async_test_client.get(
        f"/reconciliation/runs/{payload['run_id']}/findings"
    )
    assert findings_response.status_code == 200
    findings = findings_response.json()["findings"]
    assert findings[0]["finding_type"] == "missing_cashflow"


async def test_position_valuation_run_detects_inconsistent_snapshot_math(
    async_test_client: httpx.AsyncClient,
    async_db_session: AsyncSession,
    clean_db,
    ensure_reconciliation_tables,
):
    await _seed_portfolio(async_db_session, "PORT-R2")
    async_db_session.add(
        DailyPositionSnapshot(
            portfolio_id="PORT-R2",
            security_id="SEC-R2",
            date=date(2026, 3, 8),
            epoch=0,
            quantity=Decimal("10"),
            cost_basis=Decimal("90"),
            cost_basis_local=Decimal("90"),
            market_price=Decimal("11"),
            market_value=Decimal("100"),
            market_value_local=Decimal("100"),
            unrealized_gain_loss=Decimal("5"),
            unrealized_gain_loss_local=Decimal("5"),
            valuation_status="VALUED",
        )
    )
    await async_db_session.commit()

    response = await async_test_client.post(
        "/reconciliation/runs/position-valuation",
        json={"portfolio_id": "PORT-R2", "business_date": "2026-03-08"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["summary"]["finding_count"] == 2


async def test_timeseries_integrity_run_detects_aggregate_and_completeness_drift(
    async_test_client: httpx.AsyncClient,
    async_db_session: AsyncSession,
    clean_db,
    ensure_reconciliation_tables,
):
    await _seed_portfolio(async_db_session, "PORT-R3")
    await _seed_instrument(async_db_session, "SEC-R3")

    async_db_session.add_all(
        [
            DailyPositionSnapshot(
                portfolio_id="PORT-R3",
                security_id="SEC-R3",
                date=date(2026, 3, 8),
                epoch=0,
                quantity=Decimal("10"),
                cost_basis=Decimal("100"),
                cost_basis_local=Decimal("100"),
                valuation_status="VALUED",
            ),
            DailyPositionSnapshot(
                portfolio_id="PORT-R3",
                security_id="SEC-R3-MISSING",
                date=date(2026, 3, 8),
                epoch=0,
                quantity=Decimal("5"),
                cost_basis=Decimal("50"),
                cost_basis_local=Decimal("50"),
                valuation_status="VALUED",
            ),
            PositionTimeseries(
                portfolio_id="PORT-R3",
                security_id="SEC-R3",
                date=date(2026, 3, 8),
                epoch=0,
                bod_market_value=Decimal("100"),
                bod_cashflow_position=Decimal("1"),
                eod_cashflow_position=Decimal("2"),
                bod_cashflow_portfolio=Decimal("3"),
                eod_cashflow_portfolio=Decimal("4"),
                eod_market_value=Decimal("105"),
                fees=Decimal("1"),
                quantity=Decimal("10"),
                cost=Decimal("100"),
            ),
            PortfolioTimeseries(
                portfolio_id="PORT-R3",
                date=date(2026, 3, 8),
                epoch=0,
                bod_market_value=Decimal("90"),
                bod_cashflow=Decimal("1"),
                eod_cashflow=Decimal("2"),
                eod_market_value=Decimal("95"),
                fees=Decimal("0.5"),
            ),
        ]
    )
    await async_db_session.commit()

    response = await async_test_client.post(
        "/reconciliation/runs/timeseries-integrity",
        json={"portfolio_id": "PORT-R3", "business_date": "2026-03-08", "epoch": 0},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["summary"]["finding_count"] == 2

    findings_response = await async_test_client.get(
        f"/reconciliation/runs/{payload['run_id']}/findings"
    )
    findings = findings_response.json()["findings"]
    assert {finding["finding_type"] for finding in findings} == {
        "position_timeseries_completeness_gap",
        "portfolio_timeseries_aggregate_mismatch",
    }
