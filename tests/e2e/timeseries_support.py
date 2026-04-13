from collections import Counter
from decimal import Decimal

import pytest

from .api_client import E2EApiClient
from .assertions import as_decimal
from .data_factory import unique_suffix

EXPECTED_TIMESERIES_ROWS = {
    "2025-08-28": {
        "SEC_EUR_STOCK": {
            "position_currency": "EUR",
            "quantity": Decimal("100"),
            "position_to_portfolio_fx_rate": Decimal("1.1"),
            "ending_market_value_portfolio_currency": Decimal("5720"),
        },
        "CASH_": {
            "position_currency": "USD",
            "quantity": Decimal("0"),
            "position_to_portfolio_fx_rate": Decimal("1"),
            "ending_market_value_portfolio_currency": Decimal("0"),
        },
        "total_ending_market_value_portfolio_currency": Decimal("5720"),
    },
    "2025-08-29": {
        "SEC_EUR_STOCK": {
            "position_currency": "EUR",
            "quantity": Decimal("100"),
            "position_to_portfolio_fx_rate": Decimal("1.2"),
            "ending_market_value_portfolio_currency": Decimal("6600"),
        },
        "CASH_": {
            "position_currency": "USD",
            "quantity": Decimal("-25"),
            "position_to_portfolio_fx_rate": Decimal("1"),
            "ending_market_value_portfolio_currency": Decimal("-25"),
        },
        "total_ending_market_value_portfolio_currency": Decimal("6575"),
    },
}

EXPECTED_PORTFOLIO_TIMESERIES = {
    "2025-08-28": {
        "beginning_market_value": Decimal("0"),
        "ending_market_value": Decimal("5720"),
        "valuation_status": "restated",
    },
    "2025-08-29": {
        "beginning_market_value": Decimal("6240"),
        "ending_market_value": Decimal("6575"),
        "valuation_status": "restated",
    },
}


def seed_two_day_timeseries_scenario(
    e2e_api_client: E2EApiClient,
    *,
    portfolio_id: str,
    stock_security_id: str,
    cash_security_id: str,
    stock_isin: str,
    cash_isin: str,
    deposit_tx_id: str,
    buy_tx_id: str,
    settle_tx_id: str,
    fee_tx_id: str,
    prices_before_transactions: bool = False,
) -> None:
    e2e_api_client.ingest(
        "/ingest/portfolios",
        {
            "portfolios": [
                {
                    "portfolio_id": portfolio_id,
                    "base_currency": "USD",
                    "open_date": "2025-01-01",
                    "risk_exposure": "High",
                    "investment_time_horizon": "Long",
                    "portfolio_type": "Discretionary",
                    "booking_center_code": "SG",
                    "client_id": "TS_CIF",
                    "status": "Active",
                }
            ]
        },
    )
    e2e_api_client.ingest(
        "/ingest/instruments",
        {
            "instruments": [
                {
                    "security_id": stock_security_id,
                    "name": "Euro Stock",
                    "isin": stock_isin,
                    "currency": "EUR",
                    "product_type": "Equity",
                },
                {
                    "security_id": cash_security_id,
                    "name": "US Dollar",
                    "isin": cash_isin,
                    "currency": "USD",
                    "product_type": "Cash",
                },
            ]
        },
    )
    e2e_api_client.ingest(
        "/ingest/fx-rates",
        {
            "fx_rates": [
                {
                    "from_currency": "EUR",
                    "to_currency": "USD",
                    "rate_date": "2025-08-28",
                    "rate": "1.1",
                },
                {
                    "from_currency": "EUR",
                    "to_currency": "USD",
                    "rate_date": "2025-08-29",
                    "rate": "1.2",
                },
            ]
        },
    )
    e2e_api_client.ingest(
        "/ingest/business-dates",
        {"business_dates": [{"business_date": "2025-08-28"}, {"business_date": "2025-08-29"}]},
    )

    day_1_transactions = [
        {
            "transaction_id": deposit_tx_id,
            "portfolio_id": portfolio_id,
            "instrument_id": cash_security_id,
            "security_id": cash_security_id,
            "transaction_date": "2025-08-28T00:00:00Z",
            "transaction_type": "DEPOSIT",
            "quantity": 5500,
            "price": 1,
            "gross_transaction_amount": 5500,
            "trade_currency": "USD",
            "currency": "USD",
        },
        {
            "transaction_id": buy_tx_id,
            "portfolio_id": portfolio_id,
            "instrument_id": stock_security_id,
            "security_id": stock_security_id,
            "transaction_date": "2025-08-28T00:00:00Z",
            "transaction_type": "BUY",
            "quantity": 100,
            "price": 50,
            "gross_transaction_amount": 5000,
            "trade_currency": "EUR",
            "currency": "EUR",
        },
        {
            "transaction_id": settle_tx_id,
            "portfolio_id": portfolio_id,
            "instrument_id": cash_security_id,
            "security_id": cash_security_id,
            "transaction_date": "2025-08-28T00:00:00Z",
            "transaction_type": "SELL",
            "quantity": 5500,
            "price": 1,
            "gross_transaction_amount": 5500,
            "trade_currency": "USD",
            "currency": "USD",
        },
    ]
    day_2_transactions = [
        {
            "transaction_id": fee_tx_id,
            "portfolio_id": portfolio_id,
            "instrument_id": cash_security_id,
            "security_id": cash_security_id,
            "transaction_date": "2025-08-29T00:00:00Z",
            "transaction_type": "FEE",
            "quantity": 1,
            "price": 25,
            "gross_transaction_amount": 25,
            "trade_currency": "USD",
            "currency": "USD",
        }
    ]
    market_prices = [
        {
            "security_id": stock_security_id,
            "price_date": "2025-08-28",
            "price": 52,
            "currency": "EUR",
        },
        {
            "security_id": stock_security_id,
            "price_date": "2025-08-29",
            "price": 55,
            "currency": "EUR",
        },
        {
            "security_id": cash_security_id,
            "price_date": "2025-08-29",
            "price": 1,
            "currency": "USD",
        },
    ]

    if prices_before_transactions:
        e2e_api_client.ingest("/ingest/market-prices", {"market_prices": market_prices})
        e2e_api_client.ingest(
            "/ingest/transactions",
            {"transactions": [*day_1_transactions, *day_2_transactions]},
        )
        return

    e2e_api_client.ingest("/ingest/transactions", {"transactions": day_1_transactions})
    e2e_api_client.ingest("/ingest/market-prices", {"market_prices": [market_prices[0]]})
    e2e_api_client.ingest("/ingest/transactions", {"transactions": day_2_transactions})
    e2e_api_client.ingest("/ingest/market-prices", {"market_prices": market_prices[1:]})


@pytest.fixture(scope="module")
def setup_timeseries_data(clean_db_module, e2e_api_client: E2EApiClient):
    suffix = unique_suffix()
    portfolio_id = f"E2E_TS_{suffix}"
    stock_security_id = f"SEC_EUR_STOCK_{suffix}"
    cash_security_id = f"CASH_{suffix}"
    stock_isin = f"EU{suffix}"
    cash_isin = f"USD_CASH_{suffix}"
    deposit_tx_id = f"TS_DEP_{suffix}"
    buy_tx_id = f"TS_BUY_{suffix}"
    settle_tx_id = f"TS_CASH_SETTLE_BUY_{suffix}"
    fee_tx_id = f"TS_FEE_{suffix}"

    seed_two_day_timeseries_scenario(
        e2e_api_client,
        portfolio_id=portfolio_id,
        stock_security_id=stock_security_id,
        cash_security_id=cash_security_id,
        stock_isin=stock_isin,
        cash_isin=cash_isin,
        deposit_tx_id=deposit_tx_id,
        buy_tx_id=buy_tx_id,
        settle_tx_id=settle_tx_id,
        fee_tx_id=fee_tx_id,
    )

    e2e_api_client.poll_for_data(
        f"/portfolios/{portfolio_id}/positions",
        lambda data: has_expected_positions(
            data,
            stock_security_id=stock_security_id,
            cash_security_id=cash_security_id,
        ),
        timeout=240,
        fail_message=(
            "Pipeline did not produce the expected stock and cash positions for timeseries setup."
        ),
    )
    for valuation_date in ("2025-08-28", "2025-08-29"):
        payload = position_timeseries_request(valuation_date)
        e2e_api_client.poll_for_post_query_data(
            f"/integration/portfolios/{portfolio_id}/analytics/position-timeseries",
            payload,
            lambda data: has_expected_timeseries_rows(
                data,
                valuation_date=valuation_date,
                stock_security_id=stock_security_id,
                cash_security_id=cash_security_id,
            ),
            timeout=180,
            fail_message=(
                "Pipeline did not produce analytics position-timeseries rows for "
                f"{valuation_date}."
            ),
        )
        e2e_api_client.poll_for_post_query_data(
            f"/integration/portfolios/{portfolio_id}/analytics/portfolio-timeseries",
            portfolio_timeseries_request(valuation_date),
            lambda data: has_expected_portfolio_timeseries(
                data,
                valuation_date=valuation_date,
            ),
            timeout=180,
            fail_message=(
                "Pipeline did not produce analytics portfolio-timeseries rows for "
                f"{valuation_date}."
            ),
        )
    return {
        "portfolio_id": portfolio_id,
        "stock_security_id": stock_security_id,
        "cash_security_id": cash_security_id,
    }


def position_timeseries_request(day: str) -> dict:
    return {
        "as_of_date": day,
        "window": {"start_date": day, "end_date": day},
        "consumer_system": "lotus-performance",
        "frequency": "daily",
        "dimensions": [],
        "include_cash_flows": True,
        "filters": {},
        "page": {"page_size": 200},
    }


def portfolio_timeseries_request(day: str) -> dict:
    return {
        "as_of_date": day,
        "window": {"start_date": day, "end_date": day},
        "consumer_system": "lotus-performance",
        "frequency": "daily",
        "page": {"page_size": 200},
    }


def has_expected_portfolio_timeseries(payload: dict, *, valuation_date: str) -> bool:
    observations = payload.get("observations", [])
    if len(observations) != 1:
        return False
    observation = observations[0]
    expected = EXPECTED_PORTFOLIO_TIMESERIES[valuation_date]
    return (
        observation.get("valuation_date") == valuation_date
        and as_decimal(observation["beginning_market_value"]) == expected["beginning_market_value"]
        and as_decimal(observation["ending_market_value"]) == expected["ending_market_value"]
        and observation["valuation_status"] == expected["valuation_status"]
    )


def sum_portfolio_currency(rows: list[dict]) -> Decimal:
    total = Decimal("0")
    for row in rows:
        total += as_decimal(row["ending_market_value_portfolio_currency"])
    return total


def has_expected_positions(
    payload: dict,
    *,
    stock_security_id: str,
    cash_security_id: str,
) -> bool:
    positions = payload.get("positions", [])
    stock_row = next(
        (row for row in positions if row.get("security_id") == stock_security_id),
        None,
    )
    cash_row = next((row for row in positions if row.get("security_id") == cash_security_id), None)
    if stock_row is None or cash_row is None:
        return False
    return (
        as_decimal(stock_row["quantity"]) == Decimal("100")
        and as_decimal(cash_row["quantity"]) == Decimal("-25")
    )


def row_by_security_id(payload: dict, security_id: str) -> dict:
    return next(row for row in payload["rows"] if row["security_id"] == security_id)


def expected_row_for_security(valuation_date: str, security_id: str) -> dict:
    for prefix, expected in EXPECTED_TIMESERIES_ROWS[valuation_date].items():
        if prefix == "total_ending_market_value_portfolio_currency":
            continue
        if security_id.startswith(prefix):
            return expected
    raise KeyError(f"No expected row configured for {valuation_date=} {security_id=}")


def assert_timeseries_payload(
    payload: dict,
    *,
    valuation_date: str,
    portfolio_id: str,
    stock_security_id: str,
    cash_security_id: str,
) -> None:
    expected_for_day = EXPECTED_TIMESERIES_ROWS[valuation_date]
    assert payload["portfolio_id"] == portfolio_id
    assert payload["portfolio_currency"] == "USD"
    assert payload["reporting_currency"] == "USD"
    assert payload["frequency"] == "daily"
    assert payload["contract_version"] == "rfc_063_v1"
    assert payload["calendar_id"] == "business_date_calendar"
    assert payload["missing_observation_policy"] == "strict"
    assert payload["resolved_window"] == {"start_date": valuation_date, "end_date": valuation_date}
    assert payload["page"]["next_page_token"] is None
    assert payload["page"]["sort_key"] == "valuation_date:asc,security_id:asc"
    assert payload["page"]["returned_row_count"] == 2
    assert payload["page"]["snapshot_epoch"] >= 0
    diagnostics = payload["diagnostics"]
    assert diagnostics["missing_dates_count"] == 0
    assert diagnostics["stale_points_count"] == 0
    assert diagnostics["requested_dimensions"] == []
    assert diagnostics["cash_flows_included"] is True
    expected_quality_distribution = dict(
        Counter(row["valuation_status"] for row in payload["rows"])
    )
    assert diagnostics["quality_status_distribution"] == expected_quality_distribution

    rows = payload["rows"]
    assert len(rows) == 2
    assert {row["security_id"] for row in rows} == {stock_security_id, cash_security_id}

    for security_id in (stock_security_id, cash_security_id):
        row = row_by_security_id(payload, security_id)
        expected = expected_row_for_security(valuation_date, security_id)
        assert row["valuation_date"] == valuation_date
        assert row["position_currency"] == expected["position_currency"]
        assert row["cash_flow_currency"] == expected["position_currency"]
        assert row["dimensions"] == {}
        assert row["valuation_status"] in {"final", "restated"}
        assert (
            as_decimal(row["position_to_portfolio_fx_rate"])
            == expected["position_to_portfolio_fx_rate"]
        )
        assert as_decimal(row["portfolio_to_reporting_fx_rate"]) == Decimal("1")
        assert as_decimal(row["quantity"]) == expected["quantity"]
        assert (
            as_decimal(row["ending_market_value_portfolio_currency"])
            == expected["ending_market_value_portfolio_currency"]
        )
        assert (
            as_decimal(row["ending_market_value_reporting_currency"])
            == expected["ending_market_value_portfolio_currency"]
        )

    assert sum_portfolio_currency(rows) == expected_for_day[
        "total_ending_market_value_portfolio_currency"
    ]


def has_expected_timeseries_rows(
    payload: dict,
    *,
    valuation_date: str,
    stock_security_id: str,
    cash_security_id: str,
) -> bool:
    try:
        rows = payload.get("rows", [])
        if len(rows) != 2:
            return False
        stock_row = row_by_security_id(payload, stock_security_id)
        cash_row = row_by_security_id(payload, cash_security_id)
        stock_expected = expected_row_for_security(valuation_date, stock_security_id)
        cash_expected = expected_row_for_security(valuation_date, cash_security_id)
        actual_quality_distribution = dict(Counter(row["valuation_status"] for row in rows))
        return (
            stock_row["valuation_date"] == valuation_date
            and cash_row["valuation_date"] == valuation_date
            and stock_row["valuation_status"] in {"final", "restated"}
            and cash_row["valuation_status"] in {"final", "restated"}
            and as_decimal(stock_row["quantity"]) == stock_expected["quantity"]
            and as_decimal(cash_row["quantity"]) == cash_expected["quantity"]
            and as_decimal(stock_row["ending_market_value_portfolio_currency"])
            == stock_expected["ending_market_value_portfolio_currency"]
            and as_decimal(cash_row["ending_market_value_portfolio_currency"])
            == cash_expected["ending_market_value_portfolio_currency"]
            and payload.get("diagnostics", {}).get("quality_status_distribution")
            == actual_quality_distribution
        )
    except (KeyError, StopIteration):
        return False


def sum_external_flows_payload(cash_flows: list[dict]) -> Decimal:
    return sum(
        (
            as_decimal(flow["amount"])
            for flow in cash_flows
            if flow.get("cash_flow_type") == "external_flow"
        ),
        start=Decimal("0"),
    )
