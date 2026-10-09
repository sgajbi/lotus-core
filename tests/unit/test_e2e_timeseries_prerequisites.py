"""Reference visibility must precede financial transaction admission."""

from types import SimpleNamespace
from unittest.mock import Mock

import pytest
import requests

from tests.e2e.api_client import E2EApiClient
from tests.e2e.test_mwr_pipeline import setup_mwr_data
from tests.e2e.test_performance_pipeline import setup_performance_data
from tests.e2e.test_timeseries_convergence import (
    test_cash_only_staged_external_flows_are_not_doubled as cash_seed,
)
from tests.e2e.timeseries_support import seed_two_day_timeseries_scenario


class TransactionReached(Exception):
    pass


class ReferenceClient:
    def __init__(self, *, foreign=False):
        self.events = []
        self.foreign = foreign

    def ingest(self, endpoint, payload):
        self.events.append(endpoint)
        if endpoint == "/ingest/transactions":
            raise TransactionReached

    def wait_for_admitted_portfolio(self, portfolio_id):
        self.events.append("owned-portfolio")
        if self.foreign:
            raise PermissionError("foreign portfolio is not visible")

    def poll_for_data(self, endpoint, predicate):
        security_id = endpoint.split("security_id=", 1)[1]
        assert not predicate({"instruments": []})
        assert not predicate({"instruments": [{"security_id": "wrong"}]})
        assert predicate({"instruments": [{"security_id": security_id}]})
        self.events.append("instrument-visible")


def run_seed(client, scenario):
    if scenario == "cash":
        cash_seed(None, client)
    else:
        seed_two_day_timeseries_scenario(
            client,
            portfolio_id="P1",
            stock_security_id="STOCK",
            cash_security_id="CASH",
            stock_isin="STOCK_ISIN",
            cash_isin="CASH_ISIN",
            deposit_tx_id="DEP",
            buy_tx_id="BUY",
            settle_tx_id="SETTLE",
            fee_tx_id="FEE",
            prices_before_transactions=True,
        )


@pytest.mark.parametrize("scenario, instrument_count", [("cash", 1), ("two-day", 2)])
def test_each_owning_seed_requires_reference_visibility_before_transactions(
    scenario, instrument_count
):
    client = ReferenceClient()
    with pytest.raises(TransactionReached):
        run_seed(client, scenario)
    assert client.events.count("owned-portfolio") == 1
    assert client.events.count("instrument-visible") == instrument_count
    assert client.events.index("owned-portfolio") < client.events.index("/ingest/transactions")
    assert client.events.index("instrument-visible") < client.events.index("/ingest/transactions")
    if scenario == "two-day":
        assert client.events.index("/ingest/market-prices") < client.events.index(
            "/ingest/transactions"
        )


@pytest.mark.parametrize("scenario", ["cash", "two-day"])
def test_foreign_portfolio_stops_seed_before_transaction_publication(scenario):
    client = ReferenceClient(foreign=True)
    with pytest.raises(PermissionError, match="foreign portfolio"):
        run_seed(client, scenario)
    assert "/ingest/transactions" not in client.events


@pytest.mark.parametrize("authority", ["delayed-owned", "missing", "foreign"])
@pytest.mark.parametrize("scenario", ["performance", "mwr"])
def test_financial_fixture_requires_owned_visibility_before_publication(
    monkeypatch, authority, scenario
):
    client = E2EApiClient("http://ingestion", "http://query", "http://control")
    events = []
    portfolio_id = None
    visible = False
    elapsed = 0
    transactions = []

    def post(url, *, json, timeout):
        nonlocal portfolio_id
        events.append(url)
        assert timeout == 10
        if url.endswith("/ingest/portfolios"):
            portfolio = json["portfolios"][0]
            portfolio_id = portfolio["portfolio_id"]
            assert portfolio["tenant_id"] == client.tenant_id
        if url.endswith("/ingest/transactions"):
            assert visible, "transaction publication preceded tenant-owned portfolio visibility"
            transactions.extend(json["transactions"])
            assert all(transaction["portfolio_id"] == portfolio_id for transaction in transactions)
        return SimpleNamespace(raise_for_status=lambda: None)

    def query(endpoint):
        nonlocal visible
        assert portfolio_id is not None
        assert endpoint == f"/portfolios?portfolio_id={portfolio_id}"
        events.append("portfolio-query")
        if authority == "foreign":
            raise requests.HTTPError("foreign portfolio absent from tenant-scoped read")
        visible = authority == "delayed-owned" and events.count("portfolio-query") == 2
        data = {"portfolios": [{"portfolio_id": portfolio_id}] if visible else []}
        return SimpleNamespace(status_code=200, json=lambda: data)

    def advance_clock(interval):
        nonlocal elapsed
        assert interval == 2
        elapsed += 31

    monkeypatch.setattr(client.session, "post", post)
    monkeypatch.setattr(client, "query", query)
    monkeypatch.setattr("tests.e2e.api_client.time.time", lambda: elapsed)
    monkeypatch.setattr("tests.e2e.api_client.time.sleep", advance_clock)
    poll_db_until = Mock()

    def run_fixture():
        if scenario == "mwr":
            return setup_mwr_data.__wrapped__(None, None, client, poll_db_until)
        return setup_performance_data.__wrapped__(None, client, poll_db_until)

    try:
        if authority == "delayed-owned":
            result = run_fixture()
            assert result["portfolio_id"] == portfolio_id
            assert events.count("portfolio-query") == 2
            assert events.index("portfolio-query") < events.index(
                "http://ingestion/ingest/transactions"
            )
            assert events.count("http://ingestion/ingest/transactions") == 1
            assert events.count("http://ingestion/ingest/market-prices") == 1
            assert len(transactions) == (5 if scenario == "mwr" else 1)
            expected_poll_count = 2 if scenario == "mwr" else 1
            assert poll_db_until.call_count == expected_poll_count
            assert poll_db_until.call_args_list[0].kwargs["params"] == {
                "pid": portfolio_id,
                "date": "2025-08-31" if scenario == "mwr" else "2025-03-11",
            }
            assert all(call.kwargs["timeout"] == 180 for call in poll_db_until.call_args_list)
            if scenario == "mwr":
                assert {transaction["transaction_id"] for transaction in transactions} == set(
                    result["transaction_ids"].values()
                )
                assert poll_db_until.call_args_list[1].kwargs["params"] == {
                    "portfolio_id": portfolio_id,
                    "security_id": result["cash_security_id"],
                }
            else:
                assert result == {"portfolio_id": portfolio_id}
        else:
            with pytest.raises(
                pytest.fail.Exception, match="Tenant-owned portfolio did not materialize"
            ):
                run_fixture()
            assert events.count("portfolio-query") == 2
            assert "http://ingestion/ingest/transactions" not in events
            assert "http://ingestion/ingest/market-prices" not in events
            poll_db_until.assert_not_called()
    finally:
        client.session.close()
