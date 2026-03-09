from sqlalchemy import text
from sqlalchemy.orm import Session


def _load_rules(db_engine) -> dict[str, dict]:
    with Session(db_engine) as session:
        rows = session.execute(
            text(
                """
                SELECT transaction_type, classification, timing, is_position_flow, is_portfolio_flow
                FROM cashflow_rules
                """
            )
        ).fetchall()

    return {
        row[0]: {
            "classification": row[1],
            "timing": row[2],
            "is_position_flow": bool(row[3]),
            "is_portfolio_flow": bool(row[4]),
        }
        for row in rows
    }


def test_cashflow_rule_contract_for_core_business_flows(db_engine):
    """
    Business contract:
    - Portfolio-level cash movement flows must be marked as portfolio flows.
    - Trading/income/adjustment flows must be position flows.
    """
    rules = _load_rules(db_engine)

    portfolio_level_expectations = {
        "DEPOSIT": "CASHFLOW_IN",
        "WITHDRAWAL": "CASHFLOW_OUT",
        "FEE": "EXPENSE",
    }
    for tx_type, expected_classification in portfolio_level_expectations.items():
        assert tx_type in rules, f"Missing cashflow rule for {tx_type}"
        assert rules[tx_type]["classification"] == expected_classification
        assert rules[tx_type]["is_portfolio_flow"] is True

    position_level_expectations = {
        "BUY": "INVESTMENT_OUTFLOW",
        "SELL": "INVESTMENT_INFLOW",
        "DIVIDEND": "INCOME",
        "INTEREST": "INCOME",
        "ADJUSTMENT": "TRANSFER",
        "FX_CASH_SETTLEMENT_BUY": "FX_BUY",
        "FX_CASH_SETTLEMENT_SELL": "FX_SELL",
    }
    for tx_type, expected_classification in position_level_expectations.items():
        assert tx_type in rules, f"Missing cashflow rule for {tx_type}"
        assert rules[tx_type]["classification"] == expected_classification
        assert rules[tx_type]["is_position_flow"] is True


def test_cashflow_rule_contract_for_transfer_and_rights_family(db_engine):
    """
    Business contract:
    Corporate-action transfer and rights lifecycle events are modeled as TRANSFER
    position flows to preserve continuity in position-level analytics.
    """
    rules = _load_rules(db_engine)

    portfolio_transfer_types = {"TRANSFER_IN", "TRANSFER_OUT"}
    ca_transfer_family_types = {
        "MERGER_IN",
        "MERGER_OUT",
        "EXCHANGE_IN",
        "EXCHANGE_OUT",
        "REPLACEMENT_IN",
        "REPLACEMENT_OUT",
        "SPIN_IN",
        "SPIN_OFF",
        "DEMERGER_IN",
        "DEMERGER_OUT",
        "SPLIT",
        "REVERSE_SPLIT",
        "CONSOLIDATION",
        "BONUS_ISSUE",
        "STOCK_DIVIDEND",
        "RIGHTS_ANNOUNCE",
        "RIGHTS_ALLOCATE",
        "RIGHTS_EXPIRE",
        "RIGHTS_ADJUSTMENT",
        "RIGHTS_SELL",
        "RIGHTS_SUBSCRIBE",
        "RIGHTS_OVERSUBSCRIBE",
        "RIGHTS_REFUND",
        "RIGHTS_SHARE_DELIVERY",
    }
    income_settlement_types = {"CASH_CONSIDERATION", "CASH_IN_LIEU"}

    all_expected = portfolio_transfer_types | ca_transfer_family_types | income_settlement_types
    missing = sorted(tx_type for tx_type in all_expected if tx_type not in rules)
    assert not missing, f"Missing cashflow rules for CA/rights transfer family: {missing}"

    for tx_type in portfolio_transfer_types:
        rule = rules[tx_type]
        assert rule["classification"] == "TRANSFER"
        # External portfolio transfers are modeled as portfolio-level cash movement.
        assert rule["is_portfolio_flow"] is True

    for tx_type in ca_transfer_family_types:
        rule = rules[tx_type]
        assert rule["classification"] == "TRANSFER"
        assert rule["is_position_flow"] is True
        # CA transfer family should not be modeled as external investor cash movement.
        assert rule["is_portfolio_flow"] is False

    for tx_type in income_settlement_types:
        rule = rules[tx_type]
        assert rule["classification"] == "INCOME"
        assert rule["is_position_flow"] is True
        assert rule["is_portfolio_flow"] is False
