from decimal import Decimal

from sqlalchemy import text
from sqlalchemy.orm import Session

from .api_client import E2EApiClient
from .transaction_type_coverage_support import (
    MIN_E2E_CASHFLOW_DISTINCT_TYPES,
    SUPPORTED_TRANSACTION_TYPES,
    TRANSACTION_TYPES_WITHOUT_CASHFLOW_RULE,
    build_transaction_payloads,
    expected_cashflow_sign,
)


def test_transaction_type_coverage_fixture_is_deduplicated_and_comprehensive():
    tx_payloads = build_transaction_payloads(
        "E2E_TX_COVER_DRYRUN",
        security_id="SEC_COVER_DRYRUN",
        cash_security_id="CASH_USD_COVER_DRYRUN",
    )

    tx_ids = [item["transaction_id"] for item in tx_payloads]
    tx_types = [item["transaction_type"] for item in tx_payloads]

    assert len(tx_ids) == len(set(tx_ids))
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

    for item in transactions:
        if item["transaction_id"] in expected_ids:
            assert body["portfolio_id"] == portfolio_id
            assert Decimal(str(item["gross_transaction_amount"])) > 0
            assert item["transaction_type"] in SUPPORTED_TRANSACTION_TYPES
            assert "cashflow" in item

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
        expected_sign = expected_cashflow_sign(payload, classification)
        assert observed_sign == expected_sign, (
            f"Unexpected cashflow sign for {tx_id} ({tx_type}): "
            f"class={classification}, amount={amount}, expected_sign={expected_sign}"
        )
