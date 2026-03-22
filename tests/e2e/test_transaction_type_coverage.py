import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from cost_engine.domain.enums.transaction_type import TransactionType
from portfolio_common.ca_bundle_a_constants import (
    CA_BUNDLE_A_CASH_CONSIDERATION_TYPE,
    CA_BUNDLE_A_SOURCE_OUT_TYPES,
    CA_BUNDLE_A_TARGET_IN_TYPES,
)
from sqlalchemy import text
from sqlalchemy.orm import Session

from .api_client import E2EApiClient


def _iso_z(ts: datetime) -> str:
    return ts.replace(microsecond=0).isoformat().replace("+00:00", "Z")


SUPPORTED_TRANSACTION_TYPES = set(TransactionType.list())

TRANSFER_INFLOW_TRANSACTION_TYPES = {
    "TRANSFER_IN",
    "MERGER_IN",
    "EXCHANGE_IN",
    "REPLACEMENT_IN",
    "SPIN_IN",
    "DEMERGER_IN",
    "SPLIT",
    "BONUS_ISSUE",
    "STOCK_DIVIDEND",
    "RIGHTS_ALLOCATE",
    "RIGHTS_SHARE_DELIVERY",
    "RIGHTS_REFUND",
}

TRANSFER_OUTFLOW_TRANSACTION_TYPES = {
    "TRANSFER_OUT",
    "MERGER_OUT",
    "EXCHANGE_OUT",
    "REPLACEMENT_OUT",
    "SPIN_OFF",
    "DEMERGER_OUT",
    "REVERSE_SPLIT",
    "CONSOLIDATION",
    "RIGHTS_SUBSCRIBE",
    "RIGHTS_OVERSUBSCRIBE",
    "RIGHTS_SELL",
    "RIGHTS_EXPIRE",
}

CASH_INSTRUMENT_TYPES = {"DEPOSIT", "WITHDRAWAL", "FEE"}
TRANSACTION_TYPES_WITHOUT_CASHFLOW_RULE = {"OTHER", "FX_SPOT", "FX_FORWARD", "FX_SWAP"}
BUNDLE_A_OUT_TYPES = set(CA_BUNDLE_A_SOURCE_OUT_TYPES)
BUNDLE_A_IN_TYPES = set(CA_BUNDLE_A_TARGET_IN_TYPES)
MIN_E2E_CASHFLOW_DISTINCT_TYPES = 5


def _build_transaction_payloads(portfolio_id: str) -> list[dict]:
    """
    Generate one canonical payload per supported transaction type.
    This fixture is intentionally deduplicated (one transaction_type per item).
    """
    base_ts = datetime(2026, 3, 1, 9, 0, tzinfo=timezone.utc)
    payloads: list[dict] = []

    for idx, tx_type in enumerate(sorted(SUPPORTED_TRANSACTION_TYPES)):
        ts = base_ts + timedelta(minutes=idx)
        tx_id = f"{portfolio_id}_{tx_type}_{idx:02d}"
        security_id = "CASH_USD_COVER" if tx_type in CASH_INSTRUMENT_TYPES else "SEC_COVER"
        quantity = Decimal("1")
        price = Decimal("10")
        gross = Decimal("100")
        trade_fee = Decimal("0")

        if tx_type in {"DIVIDEND", "INTEREST"}:
            quantity = Decimal("0")
            price = Decimal("0")
        elif tx_type == "ADJUSTMENT":
            quantity = Decimal("0")
            price = Decimal("0")
        elif tx_type in {"BUY", "SELL", "FEE"}:
            trade_fee = Decimal("1.50")

        event = {
            "transaction_id": tx_id,
            "portfolio_id": portfolio_id,
            "instrument_id": security_id,
            "security_id": security_id,
            "transaction_date": _iso_z(ts),
            "transaction_type": tx_type,
            "quantity": str(quantity),
            "price": str(price),
            "gross_transaction_amount": str(gross),
            "trade_currency": "USD",
            "currency": "USD",
            "parent_event_reference": f"PARENT_{portfolio_id}",
            "linked_parent_event_id": f"CA-EVT-{portfolio_id}",
            "economic_event_id": f"EVT-{portfolio_id}",
            "linked_transaction_group_id": f"LTG-{portfolio_id}",
            "trade_fee": str(trade_fee),
        }
        if tx_type == "ADJUSTMENT":
            event["movement_direction"] = "INFLOW"
            event["adjustment_reason"] = "TEST_COVERAGE"
        if tx_type == "INTEREST":
            event["interest_direction"] = "INCOME"
        if tx_type in BUNDLE_A_OUT_TYPES:
            event["source_instrument_id"] = security_id
        if tx_type in BUNDLE_A_IN_TYPES:
            event["target_instrument_id"] = security_id
        if tx_type == CA_BUNDLE_A_CASH_CONSIDERATION_TYPE:
            link_ref = f"{portfolio_id}_ADJ_LINK_00"
            event["linked_cash_transaction_id"] = link_ref
            event["external_cash_transaction_id"] = link_ref

        payloads.append(event)

    return payloads


def _expected_cashflow_sign(payload: dict, classification: str) -> int:
    tx_type = payload["transaction_type"]
    gross = Decimal(str(payload["gross_transaction_amount"]))
    fee = Decimal(str(payload.get("trade_fee", "0")))
    quantity = Decimal(str(payload["quantity"]))

    net = gross + fee if tx_type in {"BUY", "FEE"} else gross - fee

    if tx_type == "INTEREST":
        direction = str(payload.get("interest_direction", "INCOME")).upper()
        return 1 if direction == "INCOME" else -1
    if tx_type == "ADJUSTMENT":
        return 1 if str(payload.get("movement_direction", "INFLOW")).upper() == "INFLOW" else -1

    if classification in {"INVESTMENT_INFLOW", "INCOME", "CASHFLOW_IN"}:
        return 1
    if classification in {"INVESTMENT_OUTFLOW", "EXPENSE", "CASHFLOW_OUT"}:
        return -1
    if classification == "TRANSFER":
        if tx_type in TRANSFER_INFLOW_TRANSACTION_TYPES:
            return 1
        if tx_type in TRANSFER_OUTFLOW_TRANSACTION_TYPES:
            return -1
        return 1 if quantity > 0 else -1

    # Keep "OTHER"/future classes deterministic for this fixture.
    return 1 if net >= 0 else -1


@pytest.fixture(scope="module")
def setup_transaction_type_coverage_data(clean_db_module, e2e_api_client: E2EApiClient):
    portfolio_id = f"E2E_TX_COVER_{uuid.uuid4().hex[:8].upper()}"

    e2e_api_client.ingest(
        "/ingest/portfolios",
        {
            "portfolios": [
                {
                    "portfolioId": portfolio_id,
                    "baseCurrency": "USD",
                    "openDate": "2026-01-01",
                    "cifId": "E2E_TX_COVER_CIF",
                    "status": "ACTIVE",
                    "riskExposure": "a",
                    "investmentTimeHorizon": "b",
                    "portfolioType": "c",
                    "bookingCenter": "d",
                }
            ]
        },
    )
    e2e_api_client.ingest(
        "/ingest/instruments",
        {
            "instruments": [
                {
                    "securityId": "SEC_COVER",
                    "name": "Coverage Security",
                    "isin": "COVER_SEC_001",
                    "instrumentCurrency": "USD",
                    "productType": "Equity",
                    "assetClass": "Equity",
                },
                {
                    "securityId": "CASH_USD_COVER",
                    "name": "Coverage Cash",
                    "isin": "COVER_CASH_001",
                    "instrumentCurrency": "USD",
                    "productType": "Cash",
                    "assetClass": "Cash",
                },
            ]
        },
    )

    payloads = _build_transaction_payloads(portfolio_id)
    e2e_api_client.ingest("/ingest/transactions", {"transactions": payloads})

    query_url = f"/portfolios/{portfolio_id}/transactions"
    e2e_api_client.poll_for_data(
        query_url,
        lambda data: data.get("transactions") and len(data["transactions"]) >= len(payloads),
        timeout=120,
        fail_message="Transaction type coverage transactions were not fully queryable in time.",
    )

    return {"portfolio_id": portfolio_id, "payloads": payloads}


@pytest.fixture(scope="module")
def setup_dual_leg_settlement_scenario(clean_db_module, e2e_api_client: E2EApiClient):
    """
    Business scenario:
    Upstream provides both product leg (BUY) and cash leg (ADJUSTMENT) with linkage.
    Cashflow generation should treat ADJUSTMENT leg as authoritative cash movement.
    """
    portfolio_id = f"E2E_DUAL_LEG_{uuid.uuid4().hex[:8].upper()}"
    buy_txn_id = f"{portfolio_id}_BUY_01"
    cash_txn_id = f"{portfolio_id}_ADJ_01"

    e2e_api_client.ingest(
        "/ingest/portfolios",
        {
            "portfolios": [
                {
                    "portfolioId": portfolio_id,
                    "baseCurrency": "USD",
                    "openDate": "2026-01-01",
                    "cifId": "E2E_DUAL_CIF",
                    "status": "ACTIVE",
                    "riskExposure": "a",
                    "investmentTimeHorizon": "b",
                    "portfolioType": "c",
                    "bookingCenter": "d",
                }
            ]
        },
    )
    e2e_api_client.ingest(
        "/ingest/instruments",
        {
            "instruments": [
                {
                    "securityId": "SEC_DUAL",
                    "name": "Dual Leg Security",
                    "isin": "DUAL_SEC_001",
                    "instrumentCurrency": "USD",
                    "productType": "Equity",
                    "assetClass": "Equity",
                },
                {
                    "securityId": "CASH_USD_DUAL",
                    "name": "Dual Leg Cash",
                    "isin": "DUAL_CASH_001",
                    "instrumentCurrency": "USD",
                    "productType": "Cash",
                    "assetClass": "Cash",
                },
            ]
        },
    )
    e2e_api_client.ingest(
        "/ingest/transactions",
        {
            "transactions": [
                {
                    "transaction_id": buy_txn_id,
                    "portfolio_id": portfolio_id,
                    "instrument_id": "SEC_DUAL",
                    "security_id": "SEC_DUAL",
                    "transaction_date": "2026-03-02T09:00:00Z",
                    "transaction_type": "BUY",
                    "quantity": "10",
                    "price": "100",
                    "gross_transaction_amount": "1000",
                    "trade_currency": "USD",
                    "currency": "USD",
                    "cash_entry_mode": "UPSTREAM_PROVIDED",
                    "external_cash_transaction_id": cash_txn_id,
                    "economic_event_id": f"EVT-{portfolio_id}",
                    "linked_transaction_group_id": f"LTG-{portfolio_id}",
                },
                {
                    "transaction_id": cash_txn_id,
                    "portfolio_id": portfolio_id,
                    "instrument_id": "CASH_USD_DUAL",
                    "security_id": "CASH_USD_DUAL",
                    "transaction_date": "2026-03-02T09:00:00Z",
                    "transaction_type": "ADJUSTMENT",
                    "quantity": "0",
                    "price": "0",
                    "gross_transaction_amount": "1000",
                    "trade_currency": "USD",
                    "currency": "USD",
                    "movement_direction": "OUTFLOW",
                    "originating_transaction_id": buy_txn_id,
                    "originating_transaction_type": "BUY",
                    "adjustment_reason": "BUY_SETTLEMENT",
                    "link_type": "BUY_TO_CASH",
                    "economic_event_id": f"EVT-{portfolio_id}",
                    "linked_transaction_group_id": f"LTG-{portfolio_id}",
                },
            ]
        },
    )

    e2e_api_client.poll_for_data(
        f"/portfolios/{portfolio_id}/transactions",
        lambda data: data.get("transactions") and len(data["transactions"]) >= 2,
        timeout=120,
        fail_message="Dual-leg scenario transactions not queryable in time.",
    )

    return {"portfolio_id": portfolio_id, "buy_txn_id": buy_txn_id, "cash_txn_id": cash_txn_id}


def test_transaction_type_coverage_fixture_is_deduplicated_and_comprehensive():
    tx_payloads = _build_transaction_payloads("E2E_TX_COVER_DRYRUN")

    tx_ids = [item["transaction_id"] for item in tx_payloads]
    tx_types = [item["transaction_type"] for item in tx_payloads]

    # No duplicate test records.
    assert len(tx_ids) == len(set(tx_ids))
    # Exactly one payload per supported type.
    assert len(tx_types) == len(set(tx_types))
    assert set(tx_types) == SUPPORTED_TRANSACTION_TYPES


def test_cashflow_rules_cover_every_supported_transaction_type(db_engine):
    with Session(db_engine) as session:
        rows = session.execute(text("SELECT transaction_type FROM cashflow_rules")).fetchall()

    rule_types = {row[0] for row in rows}
    missing = (SUPPORTED_TRANSACTION_TYPES - TRANSACTION_TYPES_WITHOUT_CASHFLOW_RULE) - rule_types
    assert not missing, f"Missing cashflow rules for transaction types: {sorted(missing)}"


def test_all_supported_transaction_types_are_ingestable_queryable_and_cashflowed(
    setup_transaction_type_coverage_data, e2e_api_client: E2EApiClient, db_engine, poll_db_until
):
    portfolio_id = setup_transaction_type_coverage_data["portfolio_id"]
    expected_payloads = setup_transaction_type_coverage_data["payloads"]
    expected_by_id = {item["transaction_id"]: item for item in expected_payloads}
    expected_ids = set(expected_by_id)
    expected_types = {item["transaction_type"] for item in expected_payloads}

    response = e2e_api_client.query(f"/portfolios/{portfolio_id}/transactions?limit=500")
    body = response.json()
    transactions = body.get("transactions", [])

    returned_ids = {item["transaction_id"] for item in transactions}
    returned_types = {item["transaction_type"] for item in transactions}

    assert expected_ids.issubset(returned_ids)
    assert expected_types.issubset(returned_types)
    assert body["total"] >= len(expected_payloads)

    # Meaningful API-side quality checks on returned records.
    for item in transactions:
        if item["transaction_id"] in expected_ids:
            assert body["portfolio_id"] == portfolio_id
            assert Decimal(str(item["gross_transaction_amount"])) > 0
            assert item["transaction_type"] in SUPPORTED_TRANSACTION_TYPES
            assert "cashflow" in item

    # DB-side checks ensure all transaction types completed cashflow pipeline.
    poll_db_until(
        query="""
            SELECT count(DISTINCT t.transaction_type)
            FROM transactions t
            JOIN cashflows c ON c.transaction_id = t.transaction_id
            WHERE t.portfolio_id = :portfolio_id
        """,
        params={"portfolio_id": portfolio_id},
        validation_func=lambda row: row is not None and row[0] >= MIN_E2E_CASHFLOW_DISTINCT_TYPES,
        timeout=180,
        fail_message="Cashflow generation did not complete for baseline transaction types",
    )

    with Session(db_engine) as session:
        rows = session.execute(
            text(
                """
                SELECT t.transaction_id, t.transaction_type, c.amount, c.classification,
                       c.is_position_flow, c.is_portfolio_flow
                FROM transactions t
                JOIN cashflows c ON c.transaction_id = t.transaction_id
                WHERE t.portfolio_id = :portfolio_id
                """
            ),
            {"portfolio_id": portfolio_id},
        ).fetchall()

    produced_types = {row[1] for row in rows}
    assert len(produced_types) >= MIN_E2E_CASHFLOW_DISTINCT_TYPES

    for tx_id, tx_type, amount, classification, is_position_flow, is_portfolio_flow in rows:
        payload = expected_by_id[tx_id]
        assert payload["transaction_type"] == tx_type
        assert bool(is_position_flow) or bool(is_portfolio_flow)

        observed_sign = 1 if Decimal(str(amount)) > 0 else -1
        expected_sign = _expected_cashflow_sign(payload, classification)
        assert observed_sign == expected_sign, (
            f"Unexpected cashflow sign for {tx_id} ({tx_type}): "
            f"class={classification}, amount={amount}, expected_sign={expected_sign}"
        )


def test_dual_leg_upstream_settlement_cashflow_authority(
    setup_dual_leg_settlement_scenario, e2e_api_client: E2EApiClient
):
    portfolio_id = setup_dual_leg_settlement_scenario["portfolio_id"]
    buy_txn_id = setup_dual_leg_settlement_scenario["buy_txn_id"]
    cash_txn_id = setup_dual_leg_settlement_scenario["cash_txn_id"]

    response = e2e_api_client.query(f"/portfolios/{portfolio_id}/transactions?limit=50")
    body = response.json()
    tx_by_id = {tx["transaction_id"]: tx for tx in body["transactions"]}

    assert buy_txn_id in tx_by_id
    assert cash_txn_id in tx_by_id
    assert tx_by_id[buy_txn_id]["external_cash_transaction_id"] == cash_txn_id
    assert tx_by_id[cash_txn_id]["originating_transaction_id"] == buy_txn_id
    assert tx_by_id[buy_txn_id]["cash_entry_mode"] == "UPSTREAM_PROVIDED"
    assert tx_by_id[cash_txn_id]["transaction_type"] == "ADJUSTMENT"


def test_dual_leg_upstream_settlement_position_timeseries_flows_net_to_zero(
    setup_dual_leg_settlement_scenario, e2e_api_client: E2EApiClient
):
    portfolio_id = setup_dual_leg_settlement_scenario["portfolio_id"]

    e2e_api_client.ingest(
        "/ingest/business-dates",
        {"business_dates": [{"business_date": "2026-03-02"}]},
    )
    e2e_api_client.ingest(
        "/ingest/market-prices",
        {
            "market_prices": [
                {
                    "security_id": "SEC_DUAL",
                    "price_date": "2026-03-02",
                    "price": "100",
                    "currency": "USD",
                },
                {
                    "security_id": "CASH_USD_DUAL",
                    "price_date": "2026-03-02",
                    "price": "1",
                    "currency": "USD",
                },
            ]
        },
    )

    payload = {
        "as_of_date": "2026-03-02",
        "window": {"start_date": "2026-03-02", "end_date": "2026-03-02"},
        "consumer_system": "lotus-performance",
        "frequency": "daily",
        "dimensions": [],
        "include_cash_flows": True,
        "filters": {},
        "page": {"page_size": 50},
    }

    response_payload = e2e_api_client.poll_for_post_query_data(
        f"/integration/portfolios/{portfolio_id}/analytics/position-timeseries",
        payload,
        lambda data: len(data.get("rows", [])) >= 2
        and {
            row.get("security_id")
            for row in data.get("rows", [])
            if row.get("valuation_date") == "2026-03-02"
        }
        >= {"SEC_DUAL", "CASH_USD_DUAL"},
        timeout=240,
        fail_message=(
            "Dual-leg position-timeseries rows were not available for acquisition-day validation."
        ),
    )

    row_by_security = {row["security_id"]: row for row in response_payload["rows"]}
    stock_row = row_by_security["SEC_DUAL"]
    cash_row = row_by_security["CASH_USD_DUAL"]

    stock_flow_total = sum(Decimal(str(flow["amount"])) for flow in stock_row["cash_flows"])
    cash_flow_total = sum(Decimal(str(flow["amount"])) for flow in cash_row["cash_flows"])

    assert Decimal(str(stock_row["beginning_market_value_position_currency"])) == Decimal("0")
    assert Decimal(str(stock_row["ending_market_value_position_currency"])) == Decimal("1000")
    assert stock_flow_total == Decimal("1000")
    assert cash_flow_total == Decimal("-1000")
    assert stock_flow_total + cash_flow_total == Decimal("0")
    assert [(flow["cash_flow_type"], flow["flow_scope"]) for flow in stock_row["cash_flows"]] == [
        ("internal_trade_flow", "internal")
    ]
    assert [(flow["cash_flow_type"], flow["flow_scope"]) for flow in cash_row["cash_flows"]] == [
        ("internal_trade_flow", "internal")
    ]
