"""Reference visibility must precede financial transaction admission."""

import pytest

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
