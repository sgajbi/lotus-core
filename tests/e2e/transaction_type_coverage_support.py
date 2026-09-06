from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from portfolio_common.domain.transaction.type_registry import (
    PRODUCTION_BOOKING_TRANSACTION_TYPES,
    TRANSACTION_TYPE_REGISTRY,
)

from src.services.portfolio_transaction_processing_service.app.domain.transaction import (
    corporate_action,
)

from .api_client import E2EApiClient
from .data_factory import unique_suffix

SUPPORTED_TRANSACTION_TYPES = set(PRODUCTION_BOOKING_TRANSACTION_TYPES) | {"OTHER"}

_TRANSFER_SIGNING_FAMILIES = {"transfer", "corporate_action", "rights"}
_FALLBACK_SIGNED_TRANSACTION_TYPES = {"CASH_IN_LIEU"}

TRANSFER_INFLOW_TRANSACTION_TYPES = {
    code
    for code, definition in TRANSACTION_TYPE_REGISTRY.items()
    if definition.production_booking_allowed
    and definition.lifecycle_family in _TRANSFER_SIGNING_FAMILIES
    and definition.position_effect == "increase"
    and code not in _FALLBACK_SIGNED_TRANSACTION_TYPES
} | {"RIGHTS_REFUND"}

TRANSFER_OUTFLOW_TRANSACTION_TYPES = {
    code
    for code, definition in TRANSACTION_TYPE_REGISTRY.items()
    if definition.production_booking_allowed
    and definition.lifecycle_family in _TRANSFER_SIGNING_FAMILIES
    and definition.position_effect == "decrease"
    and code not in _FALLBACK_SIGNED_TRANSACTION_TYPES
}

CASH_INSTRUMENT_TYPES = {
    code
    for code, definition in TRANSACTION_TYPE_REGISTRY.items()
    if definition.production_booking_allowed
    and definition.lifecycle_family in {"cash_movement", "expense"}
}

TRANSACTION_TYPES_WITHOUT_CASHFLOW_RULE = {
    code
    for code in SUPPORTED_TRANSACTION_TYPES
    if (
        not TRANSACTION_TYPE_REGISTRY[code].production_booking_allowed
        or TRANSACTION_TYPE_REGISTRY[code].cash_effect == "linked_cash_legs"
    )
}
BUNDLE_A_OUT_TYPES = set(corporate_action.SOURCE_BASIS_TRANSFER_TRANSACTION_TYPES)
BUNDLE_A_IN_TYPES = set(corporate_action.TARGET_BASIS_TRANSFER_TRANSACTION_TYPES)
BUNDLE_A_TYPES = set(corporate_action.BASIS_TRANSFER_CORPORATE_ACTION_TYPES)
BUNDLE_A_CHILD_ROLES = {
    "SPIN_OFF": "SOURCE_POSITION_REDUCE",
    "SPIN_IN": "TARGET_POSITION_ADD",
    "DEMERGER_OUT": "SOURCE_POSITION_REDUCE",
    "DEMERGER_IN": "TARGET_POSITION_ADD",
    "CASH_CONSIDERATION": "CASH_CONSIDERATION",
}
BUNDLE_A_COHORTS = {
    "SPIN_OFF": "SPIN",
    "SPIN_IN": "SPIN",
    "CASH_CONSIDERATION": "SPIN",
    "DEMERGER_OUT": "DEMERGER",
    "DEMERGER_IN": "DEMERGER",
}
REDEMPTION_TYPES = {
    code
    for code, definition in TRANSACTION_TYPE_REGISTRY.items()
    if definition.production_booking_allowed and definition.lifecycle_family == "redemption"
}
MIN_E2E_CASHFLOW_DISTINCT_TYPES = 5


def iso_z(ts: datetime) -> str:
    return ts.replace(microsecond=0).isoformat().replace("+00:00", "Z")


def build_transaction_payloads(
    portfolio_id: str,
    *,
    security_id: str,
    cash_security_id: str,
    redemption_security_ids: dict[str, str],
) -> list[dict]:
    """
    Generate one canonical payload per supported transaction type.
    This fixture is intentionally deduplicated (one transaction_type per item).
    """
    base_ts = datetime(2026, 3, 1, 9, 0, tzinfo=timezone.utc)
    payloads: list[dict] = []
    transaction_ids = {
        tx_type: f"{portfolio_id}_{tx_type}_{idx:02d}"
        for idx, tx_type in enumerate(sorted(SUPPORTED_TRANSACTION_TYPES))
    }

    for idx, tx_type in enumerate(sorted(SUPPORTED_TRANSACTION_TYPES)):
        ts = base_ts + timedelta(minutes=idx)
        tx_id = transaction_ids[tx_type]
        resolved_security_id = (
            cash_security_id
            if tx_type in CASH_INSTRUMENT_TYPES
            else redemption_security_ids[tx_type]
            if tx_type in REDEMPTION_TYPES
            else security_id
        )
        quantity = Decimal("1")
        price = Decimal("10")
        gross = Decimal("100")
        trade_fee = Decimal("0")

        if tx_type == "CASH_CONSIDERATION":
            quantity = Decimal("0")
            price = Decimal("0")
        elif tx_type in {"DIVIDEND", "INTEREST"}:
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
            "economic_event_id": f"EVT-{portfolio_id}",
            "linked_transaction_group_id": f"LTG-{portfolio_id}",
            "trade_fee": str(trade_fee),
        }
        if tx_type in BUNDLE_A_TYPES:
            cohort = BUNDLE_A_COHORTS[tx_type]
            event.update(
                {
                    "parent_event_reference": f"PARENT_{portfolio_id}_{cohort}",
                    "linked_parent_event_id": f"CA-EVT-{portfolio_id}-{cohort}",
                    "economic_event_id": f"EVT-{portfolio_id}-{cohort}",
                    "linked_transaction_group_id": f"LTG-{portfolio_id}-{cohort}",
                    "child_role": BUNDLE_A_CHILD_ROLES[tx_type],
                }
            )
        if tx_type in {"FX_FORWARD", "FX_SPOT", "FX_SWAP"}:
            event.update(
                {
                    "settlement_date": iso_z(ts),
                    "component_type": (
                        "FX_CASH_SETTLEMENT_BUY" if tx_type == "FX_SPOT" else "FX_CONTRACT_OPEN"
                    ),
                    "component_id": f"{tx_id}-COMPONENT",
                    "calculation_policy_id": "FX_DEFAULT_POLICY",
                    "calculation_policy_version": "1.0.0",
                    "quantity": "0",
                    "price": "0",
                    "pair_base_currency": "EUR",
                    "pair_quote_currency": "USD",
                    "fx_rate_quote_convention": "QUOTE_PER_BASE",
                    "buy_currency": "USD",
                    "sell_currency": "EUR",
                    "buy_amount": "110",
                    "sell_amount": "100",
                    "contract_rate": "1.10",
                    "spot_exposure_model": "NONE",
                    "fx_realized_pnl_mode": "NONE",
                }
            )
            if tx_type == "FX_SPOT":
                event["fx_cash_leg_role"] = "BUY"
                event["linked_fx_cash_leg_id"] = f"{tx_id}-SELL"
                event["settlement_status"] = "SETTLED"
            else:
                event["fx_contract_id"] = f"{tx_id}-CONTRACT"
                event["fx_contract_open_transaction_id"] = tx_id
            if tx_type == "FX_SWAP":
                event["swap_event_id"] = f"{tx_id}-SWAP"
                event["near_leg_group_id"] = f"{tx_id}-NEAR"
                event["far_leg_group_id"] = f"{tx_id}-FAR"
        if tx_type in REDEMPTION_TYPES:
            redeemed_quantity = "40" if tx_type == "PARTIAL_REDEMPTION" else "100"
            event.update(
                {
                    "settlement_date": iso_z(ts),
                    "settlement_cash_account_id": cash_security_id,
                    "settlement_cash_instrument_id": cash_security_id,
                    "quantity": redeemed_quantity,
                    "price": "1",
                    "gross_transaction_amount": redeemed_quantity,
                    "redemption_price_type": "PAR",
                    "principal_proceeds_local": redeemed_quantity,
                }
            )
            if tx_type == "PARTIAL_REDEMPTION":
                event.update({"old_factor": "1", "new_factor": "0.6"})
        if tx_type == "ADJUSTMENT":
            event["movement_direction"] = "INFLOW"
            event["adjustment_reason"] = "TEST_COVERAGE"
        if tx_type == "INTEREST":
            event["interest_direction"] = "INCOME"
        if tx_type in BUNDLE_A_OUT_TYPES:
            event["source_instrument_id"] = resolved_security_id
        if tx_type in BUNDLE_A_IN_TYPES:
            event["target_instrument_id"] = resolved_security_id
        if tx_type in corporate_action.QUANTITY_TRANSFER_CORPORATE_ACTION_PAIRS:
            target_type = corporate_action.QUANTITY_TRANSFER_CORPORATE_ACTION_PAIRS[tx_type]
            event["target_transaction_reference"] = transaction_ids[target_type]
            event["target_instrument_id"] = resolved_security_id
        if tx_type == "TRANSFER_OUT":
            event["external_destination_reference"] = f"CUSTODIAN-{portfolio_id}"
        if tx_type == corporate_action.CASH_CONSIDERATION_TRANSACTION_TYPE:
            link_ref = f"{portfolio_id}_ADJ_LINK_00"
            event["linked_cash_transaction_id"] = link_ref
            event["external_cash_transaction_id"] = link_ref
            event["allocated_cost_basis_local"] = "50"
            event["allocated_cost_basis_base"] = "50"
        elif tx_type == "CASH_IN_LIEU":
            event["allocated_cost_basis_local"] = "101.50"
            event["allocated_cost_basis_base"] = "101.50"

        payloads.append(event)

    return payloads


def build_redemption_acquisition_payload(
    portfolio_id: str, *, transaction_type: str, redemption_security_id: str
) -> dict:
    """Seed sufficient bond inventory before exercising each redemption lifecycle."""

    return {
        "transaction_id": f"{portfolio_id}_{transaction_type}_ACQUISITION",
        "portfolio_id": portfolio_id,
        "instrument_id": redemption_security_id,
        "security_id": redemption_security_id,
        "transaction_date": "2026-02-02T09:00:00Z",
        "transaction_type": "BUY",
        "quantity": "100",
        "price": "0.97",
        "gross_transaction_amount": "97",
        "trade_currency": "USD",
        "currency": "USD",
        "economic_event_id": f"EVT-{portfolio_id}-{transaction_type}-ACQUISITION",
        "linked_transaction_group_id": f"LTG-{portfolio_id}-{transaction_type}-ACQUISITION",
        "trade_fee": "0",
    }


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
def setup_transaction_type_coverage_data(
    clean_db_module, e2e_api_client: E2EApiClient, poll_db_until
):
    suffix = unique_suffix()
    portfolio_id = f"E2E_TX_COVER_{suffix}"
    security_id = f"SEC_COVER_{suffix}"
    cash_security_id = f"CASH_USD_COVER_{suffix}"
    redemption_security_ids = {
        tx_type: f"BOND_{tx_type}_{suffix}" for tx_type in sorted(REDEMPTION_TYPES)
    }

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
    e2e_api_client.poll_for_data(
        f"/portfolios?portfolio_id={portfolio_id}",
        lambda data: (
            [portfolio["portfolio_id"] for portfolio in data.get("portfolios", [])]
            == [portfolio_id]
        ),
        fail_message=(
            "Tenant-owned transaction-coverage portfolio did not become durable "
            "before transaction admission."
        ),
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
                *[
                    {
                        "securityId": redemption_security_ids[tx_type],
                        "name": f"Coverage {tx_type.replace('_', ' ').title()} Bond",
                        "isin": f"COVER_{tx_type}_{suffix}",
                        "instrumentCurrency": "USD",
                        "productType": "Bond",
                        "assetClass": "Fixed Income",
                    }
                    for tx_type in sorted(REDEMPTION_TYPES)
                ],
            ]
        },
    )

    payloads = build_transaction_payloads(
        portfolio_id,
        security_id=security_id,
        cash_security_id=cash_security_id,
        redemption_security_ids=redemption_security_ids,
    )
    redemption_acquisitions = [
        build_redemption_acquisition_payload(
            portfolio_id,
            transaction_type=tx_type,
            redemption_security_id=redemption_security_ids[tx_type],
        )
        for tx_type in sorted(REDEMPTION_TYPES)
    ]
    e2e_api_client.ingest("/ingest/transactions", {"transactions": redemption_acquisitions})
    acquisition_params = {
        f"acquisition_id_{index}": acquisition["transaction_id"]
        for index, acquisition in enumerate(redemption_acquisitions)
    }
    acquisition_placeholders = ", ".join(f":{name}" for name in acquisition_params)
    poll_db_until(
        query=f"""
            SELECT count(DISTINCT transaction_id)
            FROM position_history
            WHERE transaction_id IN ({acquisition_placeholders})
              AND quantity = 100
        """,
        params=acquisition_params,
        validation_func=lambda row: row is not None and row[0] == len(redemption_acquisitions),
        timeout=120,
        fail_message="Redemption acquisition positions were not fully applied",
    )

    e2e_api_client.ingest("/ingest/transactions", {"transactions": payloads})

    query_url = f"/portfolios/{portfolio_id}/transactions"
    submitted_transaction_ids = {
        transaction["transaction_id"] for transaction in [*redemption_acquisitions, *payloads]
    }
    e2e_api_client.poll_for_data(
        query_url,
        lambda data: submitted_transaction_ids.issubset(
            {transaction["transaction_id"] for transaction in data.get("transactions", [])}
        ),
        timeout=120,
        fail_message="Transaction type coverage transactions were not fully queryable in time.",
    )

    return {
        "portfolio_id": portfolio_id,
        "payloads": payloads,
        "security_id": security_id,
        "cash_security_id": cash_security_id,
        "redemption_security_ids": redemption_security_ids,
        "redemption_acquisitions": redemption_acquisitions,
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
