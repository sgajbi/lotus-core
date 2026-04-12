from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from cost_engine.domain.enums.transaction_type import TransactionType
from portfolio_common.ca_bundle_a_constants import (
    CA_BUNDLE_A_CASH_CONSIDERATION_TYPE,
    CA_BUNDLE_A_SOURCE_OUT_TYPES,
    CA_BUNDLE_A_TARGET_IN_TYPES,
)

from .api_client import E2EApiClient
from .data_factory import unique_suffix

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


def iso_z(ts: datetime) -> str:
    return ts.replace(microsecond=0).isoformat().replace("+00:00", "Z")


def build_transaction_payloads(
    portfolio_id: str, *, security_id: str, cash_security_id: str
) -> list[dict]:
    """
    Generate one canonical payload per supported transaction type.
    This fixture is intentionally deduplicated (one transaction_type per item).
    """
    base_ts = datetime(2026, 3, 1, 9, 0, tzinfo=timezone.utc)
    payloads: list[dict] = []

    for idx, tx_type in enumerate(sorted(SUPPORTED_TRANSACTION_TYPES)):
        ts = base_ts + timedelta(minutes=idx)
        tx_id = f"{portfolio_id}_{tx_type}_{idx:02d}"
        resolved_security_id = (
            cash_security_id if tx_type in CASH_INSTRUMENT_TYPES else security_id
        )
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
            "instrument_id": resolved_security_id,
            "security_id": resolved_security_id,
            "transaction_date": iso_z(ts),
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
            event["source_instrument_id"] = resolved_security_id
        if tx_type in BUNDLE_A_IN_TYPES:
            event["target_instrument_id"] = resolved_security_id
        if tx_type == CA_BUNDLE_A_CASH_CONSIDERATION_TYPE:
            link_ref = f"{portfolio_id}_ADJ_LINK_00"
            event["linked_cash_transaction_id"] = link_ref
            event["external_cash_transaction_id"] = link_ref

        payloads.append(event)

    return payloads


def expected_cashflow_sign(payload: dict, classification: str) -> int:
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

    return 1 if net >= 0 else -1


@pytest.fixture(scope="module")
def setup_transaction_type_coverage_data(clean_db_module, e2e_api_client: E2EApiClient):
    suffix = unique_suffix()
    portfolio_id = f"E2E_TX_COVER_{suffix}"
    security_id = f"SEC_COVER_{suffix}"
    cash_security_id = f"CASH_USD_COVER_{suffix}"

    e2e_api_client.ingest(
        "/ingest/portfolios",
        {
            "portfolios": [
                {
                    "portfolioId": portfolio_id,
                    "baseCurrency": "USD",
                    "openDate": "2026-01-01",
                    "cifId": f"E2E_TX_COVER_CIF_{suffix}",
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
                    "securityId": security_id,
                    "name": "Coverage Security",
                    "isin": f"COVER_SEC_{suffix}",
                    "instrumentCurrency": "USD",
                    "productType": "Equity",
                    "assetClass": "Equity",
                },
                {
                    "securityId": cash_security_id,
                    "name": "Coverage Cash",
                    "isin": f"COVER_CASH_{suffix}",
                    "instrumentCurrency": "USD",
                    "productType": "Cash",
                    "assetClass": "Cash",
                },
            ]
        },
    )

    payloads = build_transaction_payloads(
        portfolio_id, security_id=security_id, cash_security_id=cash_security_id
    )
    e2e_api_client.ingest("/ingest/transactions", {"transactions": payloads})

    query_url = f"/portfolios/{portfolio_id}/transactions"
    e2e_api_client.poll_for_data(
        query_url,
        lambda data: data.get("transactions") and len(data["transactions"]) >= len(payloads),
        timeout=120,
        fail_message="Transaction type coverage transactions were not fully queryable in time.",
    )

    return {
        "portfolio_id": portfolio_id,
        "payloads": payloads,
        "security_id": security_id,
        "cash_security_id": cash_security_id,
    }


@pytest.fixture(scope="module")
def setup_dual_leg_settlement_scenario(clean_db_module, e2e_api_client: E2EApiClient):
    suffix = unique_suffix()
    portfolio_id = f"E2E_DUAL_LEG_{suffix}"
    buy_txn_id = f"{portfolio_id}_BUY_01"
    cash_txn_id = f"{portfolio_id}_ADJ_01"
    security_id = f"SEC_DUAL_{suffix}"
    cash_security_id = f"CASH_USD_DUAL_{suffix}"

    e2e_api_client.ingest(
        "/ingest/portfolios",
        {
            "portfolios": [
                {
                    "portfolioId": portfolio_id,
                    "baseCurrency": "USD",
                    "openDate": "2026-01-01",
                    "cifId": f"E2E_DUAL_CIF_{suffix}",
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
                    "securityId": security_id,
                    "name": "Dual Leg Security",
                    "isin": f"DUAL_SEC_{suffix}",
                    "instrumentCurrency": "USD",
                    "productType": "Equity",
                    "assetClass": "Equity",
                },
                {
                    "securityId": cash_security_id,
                    "name": "Dual Leg Cash",
                    "isin": f"DUAL_CASH_{suffix}",
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
                    "instrument_id": security_id,
                    "security_id": security_id,
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
                    "instrument_id": cash_security_id,
                    "security_id": cash_security_id,
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

    return {
        "portfolio_id": portfolio_id,
        "buy_txn_id": buy_txn_id,
        "cash_txn_id": cash_txn_id,
        "security_id": security_id,
        "cash_security_id": cash_security_id,
    }
