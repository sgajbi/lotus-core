"""Registered QCP HTTP ownership must precede analytics observations and identities."""

import json
from datetime import UTC, date, datetime
from decimal import Decimal

import httpx
import pytest
from portfolio_common import db as database_provider
from portfolio_common.database_models import (
    BusinessDate,
    Instrument,
    Portfolio,
    PortfolioTimeseries,
    PositionHistory,
    PositionState,
    PositionTimeseries,
    Transaction,
)
from sqlalchemy.ext.asyncio import async_sessionmaker

from src.services.query_control_plane_service.app.main import app

pytestmark = [pytest.mark.asyncio, pytest.mark.db_direct]
DAYS = (date(2026, 4, 10), date(2026, 4, 13))
OWNERS = (
    ("tenant-analytics-a", "ANALYTICS_OWNER_A", "100"),
    ("tenant-analytics-b", "ANALYTICS_OWNER_B", "300"),
)
SECURITY = "ANALYTICS_OWNER_SECURITY"


@pytest.mark.parametrize("dataset", ["portfolio", "position"])
async def test_registered_http_analytics_tenant_ownership(
    clean_db, async_db_session, monkeypatch, dataset
):
    """Use the real admission, composition, snapshot, service and PostgreSQL reader."""
    session = async_db_session
    session.add(
        Instrument(
            security_id=SECURITY,
            name="Analytics ownership equity",
            isin="ANALYTICS-OWNER",
            currency="USD",
            product_type="EQUITY",
            asset_class="Equity",
        )
    )
    session.add_all(BusinessDate(date=day) for day in DAYS)
    for tenant, portfolio, amount in OWNERS:
        session.add(
            Portfolio(
                tenant_id=tenant,
                portfolio_id=portfolio,
                base_currency="USD",
                open_date=DAYS[0],
                risk_exposure="BALANCED",
                investment_time_horizon="LONG_TERM",
                portfolio_type="discretionary",
                booking_center_code="Singapore",
                client_id=f"CLIENT_{portfolio}",
                status="active",
            )
        )
    await session.flush()
    for _, portfolio, amount in OWNERS:
        session.add(
            Transaction(
                transaction_id=f"{portfolio}_BUY",
                portfolio_id=portfolio,
                instrument_id=SECURITY,
                security_id=SECURITY,
                transaction_date=datetime(2026, 4, 10, 9, tzinfo=UTC),
                settlement_date=datetime(2026, 4, 10, 16, tzinfo=UTC),
                transaction_type="BUY",
                quantity=Decimal("10"),
                price=Decimal(amount) / 10,
                gross_transaction_amount=Decimal(amount),
                trade_currency="USD",
                currency="USD",
            )
        )
    await session.flush()
    for _, portfolio, amount in OWNERS:
        # Source admission requires a same-epoch historical quantity; a valuation
        # row alone cannot establish a supported current holding.
        session.add(
            PositionHistory(
                portfolio_id=portfolio,
                security_id=SECURITY,
                transaction_id=f"{portfolio}_BUY",
                position_date=DAYS[0],
                epoch=0,
                quantity=Decimal("10"),
                cost_basis=Decimal(amount),
                cost_basis_local=Decimal(amount),
            )
        )
        session.add(
            PositionState(
                portfolio_id=portfolio,
                security_id=SECURITY,
                epoch=0,
                watermark_date=DAYS[-1],
                status="CURRENT",
            )
        )
        for day in DAYS:
            value = Decimal(amount)
            session.add(
                PortfolioTimeseries(
                    portfolio_id=portfolio,
                    date=day,
                    epoch=0,
                    bod_market_value=value,
                    eod_market_value=value + 1,
                    bod_cashflow=0,
                    eod_cashflow=0,
                    fees=0,
                )
            )
            session.add(
                PositionTimeseries(
                    portfolio_id=portfolio,
                    security_id=SECURITY,
                    date=day,
                    epoch=0,
                    bod_market_value=value,
                    eod_market_value=value + 1,
                    bod_cashflow_position=0,
                    eod_cashflow_position=0,
                    bod_cashflow_portfolio=0,
                    eod_cashflow_portfolio=0,
                    fees=0,
                    quantity=10,
                    cost=value,
                )
            )
    await session.commit()
    monkeypatch.setattr(
        database_provider,
        "AsyncSessionLocal",
        async_sessionmaker(bind=session.bind, expire_on_commit=False),
    )
    body = {
        "as_of_date": DAYS[-1].isoformat(),
        "window": {"start_date": DAYS[0].isoformat(), "end_date": DAYS[-1].isoformat()},
        "page": {"page_size": 1},
    }
    if dataset == "position":
        body["include_cash_flows"] = False

    def endpoint(portfolio):
        return f"/integration/portfolios/{portfolio}/analytics/{dataset}-timeseries"

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        for tenant, portfolio, amount in OWNERS:
            owned = await client.post(
                endpoint(portfolio), headers={"X-Tenant-Id": tenant}, json=body
            )
            assert owned.status_code == 200, owned.text
            data = owned.json()
            rows = data["observations" if dataset == "portfolio" else "rows"]
            assert len(rows) == 1
            value_key = (
                "ending_market_value"
                if dataset == "portfolio"
                else "ending_market_value_portfolio_currency"
            )
            assert Decimal(rows[0][value_key]) == Decimal(amount) + 1
            # Nullable response provenance is independent of admitted access authority.
            assert data["tenant_id"] is None
            repeated = await client.post(
                endpoint(portfolio), headers={"X-Tenant-Id": tenant}, json=body
            )
            assert repeated.status_code == 200, repeated.text
            assert repeated.json()["content_hash"] == data["content_hash"]
            assert (
                repeated.json()["lineage"]["request_fingerprint"]
                == data["lineage"]["request_fingerprint"]
            )
            token = data["page"]["next_page_token"]
            assert token
            continuation = {**body, "page": {"page_size": 1, "page_token": token}}
            next_page = await client.post(
                endpoint(portfolio), headers={"X-Tenant-Id": tenant}, json=continuation
            )
            assert next_page.status_code == 200, next_page.text
            assert (
                next_page.json()["page"]["request_scope_fingerprint"]
                == data["page"]["request_scope_fingerprint"]
            )
            foreign = next(owner[0] for owner in OWNERS if owner[0] != tenant)
            for selection in (
                body,
                continuation,
                {**body, "period": "inception", "window": None},
                {**body, "tenant_id": tenant},
                {**body, "page": {"page_size": 1, "page_token": "invalid-token"}},
            ):
                if dataset == "position":
                    selection = {
                        **selection,
                        "filters": {
                            "security_ids": [SECURITY],
                            "position_ids": [f"{portfolio}:{SECURITY}"],
                        },
                    }
                refused = await client.post(
                    endpoint(portfolio), headers={"X-Tenant-Id": foreign}, json=selection
                )
                missing = await client.post(
                    endpoint("ANALYTICS_MISSING"), headers={"X-Tenant-Id": foreign}, json=selection
                )
                assert refused.status_code == missing.status_code == 404
                problems = []
                for response in (refused, missing):
                    problem = response.json()
                    assert problem["error_code"] == "QCP_ANALYTICS_NOT_FOUND"
                    assert problem["detail"] == "Requested analytics source was not found."
                    # Existing problem instances echo the caller's own request path;
                    # correlation IDs identify each call. Neither identifies source state.
                    assert problem.pop("instance").startswith("/integration/portfolios/")
                    assert problem.pop("correlation_id")
                    safe_payload = json.dumps(problem)
                    assert portfolio not in safe_payload
                    assert tenant not in safe_payload
                    for source_field in (
                        "fingerprint",
                        "observations",
                        "lineage",
                        "content_hash",
                        "source_digest",
                        "rows",
                    ):
                        assert source_field not in safe_payload
                    problems.append(problem)
                assert problems[0] == problems[1]
            if dataset == "portfolio":
                reference = f"/integration/portfolios/{portfolio}/analytics/reference"
                reference_body = {"as_of_date": DAYS[-1].isoformat()}
                owned_reference = await client.post(
                    reference, headers={"X-Tenant-Id": tenant}, json=reference_body
                )
                assert owned_reference.status_code == 200, owned_reference.text
                foreign_reference = await client.post(
                    reference, headers={"X-Tenant-Id": foreign}, json=reference_body
                )
                assert foreign_reference.status_code == 404, foreign_reference.text
                reference_problem = foreign_reference.json()
                assert reference_problem.pop("instance") == reference
                assert portfolio not in json.dumps(reference_problem)
                assert "fingerprint" not in foreign_reference.text
        for headers in ({}, {"X-Tenant-Id": " "}):
            response = await client.post(endpoint(OWNERS[0][1]), headers=headers, json=body)
            assert response.status_code == 401, response.text
            assert "fingerprint" not in response.text
