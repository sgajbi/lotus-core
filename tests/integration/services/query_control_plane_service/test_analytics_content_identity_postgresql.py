"""Actual PostgreSQL source corrections must reach both HTTP content identities."""

import logging
from datetime import UTC, date, datetime
from decimal import Decimal
from unittest.mock import MagicMock

import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI
from portfolio_common.database_models import (
    BusinessDate,
    Cashflow,
    FxRate,
    Instrument,
    Portfolio,
    PositionHistory,
    PositionState,
    PositionTimeseries,
    Transaction,
)
from sqlalchemy import delete, update

from src.services.query_control_plane_service.app.application.analytics.analytics_timeseries_service import (  # noqa: E501
    AnalyticsRuntimePolicy,
    AnalyticsTimeseriesService,
)
from src.services.query_control_plane_service.app.dependencies import (
    get_analytics_timeseries_service,
)
from src.services.query_control_plane_service.app.exception_mappers import (
    register_query_control_plane_exception_handlers,
)
from src.services.query_control_plane_service.app.infrastructure.analytics_export_repository import (  # noqa: E501
    AnalyticsExportRepository,
)
from src.services.query_control_plane_service.app.infrastructure.analytics_timeseries_repository import (  # noqa: E501
    AnalyticsTimeseriesRepository,
)
from src.services.query_control_plane_service.app.infrastructure.analytics_unit_of_work import (  # noqa: E501
    SqlAlchemyAnalyticsUnitOfWork,
)
from src.services.query_control_plane_service.app.routers.analytics_inputs import router

pytestmark = [pytest.mark.asyncio, pytest.mark.db_direct, pytest.mark.lifecycle]
PORTFOLIO_ID = "CONTENT_IDENTITY_PG"
SECURITY_ID = "CONTENT_IDENTITY_EQUITY"
TRANSACTION_ID = "CONTENT_IDENTITY_FLOW"
FIRST_DAY = date(2026, 4, 10)
LAST_DAY = date(2026, 4, 13)


@pytest_asyncio.fixture
async def content_identity_client(clean_db, async_db_session, monkeypatch):
    """Own only the HTTP client; borrow the governed fixture's PostgreSQL session."""

    serving_clock = MagicMock(wraps=datetime)
    serving_clock.now.side_effect = [
        datetime(2026, 10, 8, 1, 0, second, tzinfo=UTC) for second in range(10)
    ]
    monkeypatch.setattr(
        "src.services.query_control_plane_service.app.application.analytics."
        "analytics_timeseries_service.datetime",
        serving_clock,
    )
    session = async_db_session
    session.add(
        Portfolio(
            tenant_id="tenant-content-identity",
            portfolio_id=PORTFOLIO_ID,
            base_currency="USD",
            open_date=FIRST_DAY,
            risk_exposure="moderate",
            investment_time_horizon="long_term",
            portfolio_type="discretionary",
            booking_center_code="Singapore",
            client_id="CLIENT_CONTENT_IDENTITY",
            status="ACTIVE",
        )
    )
    session.add(
        Instrument(
            security_id=SECURITY_ID,
            name="Content identity equity",
            isin="CONTENT-IDENTITY-PG",
            currency="USD",
            product_type="EQUITY",
            asset_class="Equity",
        )
    )
    session.add_all(BusinessDate(date=day) for day in (FIRST_DAY, LAST_DAY))
    await session.flush()
    session.add(
        Transaction(
            transaction_id=TRANSACTION_ID,
            portfolio_id=PORTFOLIO_ID,
            instrument_id=SECURITY_ID,
            security_id=SECURITY_ID,
            transaction_date=datetime(2026, 4, 10, 9, tzinfo=UTC),
            settlement_date=datetime(2026, 4, 10, 16, tzinfo=UTC),
            transaction_type="BUY",
            quantity=Decimal("10"),
            price=Decimal("10"),
            gross_transaction_amount=Decimal("100"),
            trade_currency="USD",
            currency="USD",
        )
    )
    await session.flush()
    session.add(
        PositionState(
            portfolio_id=PORTFOLIO_ID,
            security_id=SECURITY_ID,
            epoch=1,
            watermark_date=LAST_DAY,
            status="CURRENT",
        )
    )
    for day, beginning, ending in ((FIRST_DAY, "100", "110"), (LAST_DAY, "110", "120")):
        session.add(
            PositionHistory(
                portfolio_id=PORTFOLIO_ID,
                security_id=SECURITY_ID,
                transaction_id=TRANSACTION_ID,
                position_date=day,
                epoch=1,
                quantity=Decimal("10"),
                cost_basis=Decimal("100"),
                cost_basis_local=Decimal("100"),
            )
        )
        session.add(
            PositionTimeseries(
                portfolio_id=PORTFOLIO_ID,
                security_id=SECURITY_ID,
                date=day,
                epoch=1,
                bod_market_value=Decimal(beginning),
                eod_market_value=Decimal(ending),
                bod_cashflow_position=Decimal("0"),
                eod_cashflow_position=Decimal("0"),
                bod_cashflow_portfolio=Decimal("0"),
                eod_cashflow_portfolio=Decimal("0"),
                fees=Decimal("0"),
                quantity=Decimal("10"),
                cost=Decimal("100"),
            )
        )
        session.add(
            FxRate(from_currency="USD", to_currency="SGD", rate_date=day, rate=Decimal("2"))
        )
    session.add(
        Cashflow(
            transaction_id=TRANSACTION_ID,
            portfolio_id=PORTFOLIO_ID,
            security_id=SECURITY_ID,
            cashflow_date=FIRST_DAY,
            epoch=1,
            amount=Decimal("5"),
            currency="USD",
            classification="CASHFLOW_IN",
            timing="EOD",
            calculation_type="SOURCE",
            is_position_flow=True,
            is_portfolio_flow=True,
        )
    )
    await session.commit()
    service = AnalyticsTimeseriesService(
        reader=AnalyticsTimeseriesRepository(session),
        export_store=AnalyticsExportRepository(session),
        unit_of_work=SqlAlchemyAnalyticsUnitOfWork(session),
        policy=AnalyticsRuntimePolicy(
            page_token_secret="content-identity-test-key",
            page_token_key_id="k1",
            page_token_previous_keys={},
            page_token_ttl_seconds=900,
            export_stale_timeout_minutes=15,
            export_execution_timeout_seconds=300,
        ),
    )
    app = FastAPI()
    app.include_router(router)
    register_query_control_plane_exception_handlers(app, logger=logging.getLogger(__name__))
    app.dependency_overrides[get_analytics_timeseries_service] = lambda: service
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        yield client, session


async def read_page(client, dataset, **page):
    return await client.post(
        f"/integration/portfolios/{PORTFOLIO_ID}/analytics/{dataset}-timeseries",
        json={
            "as_of_date": LAST_DAY.isoformat(),
            "window": {"start_date": FIRST_DAY.isoformat(), "end_date": LAST_DAY.isoformat()},
            "reporting_currency": "SGD",
            "page": {"page_size": 10, **page},
        },
    )


def economic_rows(payload, dataset):
    return payload["observations" if dataset == "portfolio" else "rows"]


def ending_value(row, dataset):
    return Decimal(
        row[
            "ending_market_value"
            if dataset == "portfolio"
            else "ending_market_value_reporting_currency"
        ]
    )


@pytest.mark.parametrize("dataset", ["portfolio", "position"])
@pytest.mark.parametrize("correction", ["valuation", "fx", "flow"])
async def test_db_corrections_change_http_content_but_not_request_identity(
    content_identity_client, dataset, correction
):
    client, session = content_identity_client
    original = await read_page(client, dataset)
    repeated = await read_page(client, dataset)
    assert original.status_code == repeated.status_code == 200
    before, repeat = original.json(), repeated.json()
    assert before["content_hash"] == repeat["content_hash"] == before["source_digest"]
    assert before["lineage"]["generated_at"] != repeat["lineage"]["generated_at"]
    assert ending_value(economic_rows(before, dataset)[0], dataset) == Decimal("220")
    if correction == "valuation":
        statement = (
            update(PositionTimeseries)
            .where(
                PositionTimeseries.portfolio_id == PORTFOLIO_ID,
                PositionTimeseries.date == FIRST_DAY,
            )
            .values(eod_market_value=Decimal("115"))
        )
    elif correction == "fx":
        statement = update(FxRate).where(FxRate.rate_date == FIRST_DAY).values(rate=Decimal("3"))
    else:
        statement = (
            update(Cashflow)
            .where(Cashflow.transaction_id == TRANSACTION_ID)
            .values(amount=Decimal("7"))
        )
    await session.execute(statement)
    await session.commit()
    corrected_response = await read_page(client, dataset)
    assert corrected_response.status_code == 200
    after = corrected_response.json()
    assert before["content_hash"] != after["content_hash"] == after["source_digest"]
    assert before["lineage"]["request_fingerprint"] == after["lineage"]["request_fingerprint"]
    assert before["page"]["snapshot_epoch"] == after["page"]["snapshot_epoch"] == 1
    corrected_row = economic_rows(after, dataset)[0]
    expected_ending = {"valuation": "230", "fx": "330", "flow": "220"}[correction]
    assert ending_value(corrected_row, dataset) == Decimal(expected_ending)
    if correction == "flow":
        assert Decimal(corrected_row["cash_flows"][0]["amount"]) == Decimal(
            "14" if dataset == "portfolio" else "7"
        )
    assert after["source_cut_id"] is None
    assert after["source_lineage"]["content_identity_scope"] == "response_page"
    assert after["source_lineage"]["source_cut_status"] == "UNAVAILABLE"


@pytest.mark.parametrize("dataset", ["portfolio", "position"])
async def test_http_paging_is_page_identity_not_complete_cut(content_identity_client, dataset):
    client, _ = content_identity_client
    first_response = await read_page(client, dataset, page_size=1)
    assert first_response.status_code == 200
    first = first_response.json()
    token = first["page"]["next_page_token"]
    assert token is not None
    second_response = await read_page(client, dataset, page_size=1, page_token=token)
    repeated = await read_page(client, dataset, page_size=1)
    assert second_response.status_code == repeated.status_code == 200
    second = second_response.json()
    assert first["content_hash"] == repeated.json()["content_hash"] != second["content_hash"]
    assert ending_value(economic_rows(first, dataset)[0], dataset) == Decimal("220")
    assert ending_value(economic_rows(second, dataset)[0], dataset) == Decimal("240")
    for payload in (first, second):
        assert payload["data_quality_status"] == "PARTIAL"
        assert payload["source_cut_id"] is None
        assert payload["source_lineage"]["content_identity_scope"] == "response_page"


@pytest.mark.parametrize("dataset", ["portfolio", "position"])
async def test_missing_fx_refuses_http_economics_not_a_usable_empty_digest(
    content_identity_client, dataset
):
    client, session = content_identity_client
    await session.execute(delete(FxRate).where(FxRate.rate_date == FIRST_DAY))
    await session.commit()
    response = await read_page(client, dataset)
    assert response.status_code == 422
    assert response.json()["error_code"] == "QCP_ANALYTICS_INSUFFICIENT_DATA"
    assert "content_hash" not in response.json()
