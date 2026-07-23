"""Test FX validation rules and stable reason codes."""

from dataclasses import replace
from datetime import datetime
from decimal import Decimal

import pytest

from src.services.portfolio_transaction_processing_service.app.domain.transaction.fx import (
    FxCanonicalTransaction,
    FxValidationReasonCode,
    validate_fx_transaction,
)


def _base_txn() -> FxCanonicalTransaction:
    return FxCanonicalTransaction(
        transaction_id="FX-VAL-001",
        transaction_type="FX_FORWARD",
        component_type="FX_CONTRACT_OPEN",
        component_id="FX-COMP-OPEN-001",
        linked_component_ids=["FX-COMP-BUY-001", "FX-COMP-SELL-001"],
        portfolio_id="PORT-001",
        instrument_id="FXC-EURUSD-001",
        security_id="FXC-EURUSD-001",
        transaction_date=datetime(2026, 4, 1, 9, 0, 0),
        settlement_date=datetime(2026, 7, 1, 9, 0, 0),
        quantity=Decimal("0"),
        price=Decimal("0"),
        gross_transaction_amount=Decimal("1095000"),
        trade_currency="USD",
        currency="USD",
        pair_base_currency="EUR",
        pair_quote_currency="USD",
        fx_rate_quote_convention="QUOTE_PER_BASE",
        buy_currency="USD",
        sell_currency="EUR",
        buy_amount=Decimal("1095000"),
        sell_amount=Decimal("1000000"),
        contract_rate=Decimal("1.095"),
        economic_event_id="EVT-FX-001",
        linked_transaction_group_id="LTG-FX-001",
        calculation_policy_id="FX_DEFAULT_POLICY",
        calculation_policy_version="1.0.0",
        fx_contract_id="FXC-2026-0001",
        spot_exposure_model="NONE",
        fx_realized_pnl_mode="UPSTREAM_PROVIDED",
        realized_capital_pnl_local=Decimal("0"),
        realized_fx_pnl_local=Decimal("1250"),
        realized_total_pnl_local=Decimal("1250"),
        realized_capital_pnl_base=Decimal("0"),
        realized_fx_pnl_base=Decimal("1250"),
        realized_total_pnl_base=Decimal("1250"),
    )


def test_validate_fx_transaction_happy_path() -> None:
    issues = validate_fx_transaction(_base_txn(), strict_metadata=True)
    assert issues == []


def test_validate_fx_transaction_normalizes_control_codes() -> None:
    txn = replace(
        _base_txn(),
        **{
            "transaction_type": " fx_forward ",
            "component_type": " fx_contract_open ",
            "fx_rate_quote_convention": " quote_per_base ",
            "spot_exposure_model": " none ",
            "fx_realized_pnl_mode": " upstream_provided ",
        },
    )

    issues = validate_fx_transaction(txn, strict_metadata=True)

    assert issues == []


def test_validate_fx_transaction_normalizes_cash_leg_role() -> None:
    txn = replace(
        _base_txn(),
        **{
            "component_type": " fx_cash_settlement_buy ",
            "fx_cash_leg_role": " buy ",
            "linked_fx_cash_leg_id": "FX-CASH-SELL-001",
        },
    )

    issues = validate_fx_transaction(txn)

    assert issues == []


def test_validate_fx_transaction_rejects_unknown_business_type() -> None:
    txn = replace(_base_txn(), transaction_type="BUY")
    issues = validate_fx_transaction(txn)
    assert any(i.code == FxValidationReasonCode.INVALID_TRANSACTION_TYPE for i in issues)


def test_validate_fx_transaction_rejects_unknown_component_type() -> None:
    txn = replace(_base_txn(), component_type="UNKNOWN")
    issues = validate_fx_transaction(txn)
    assert any(i.code == FxValidationReasonCode.INVALID_COMPONENT_TYPE for i in issues)


def test_validate_fx_transaction_rejects_non_zero_quantity_and_price() -> None:
    txn = replace(_base_txn(), quantity=Decimal("1"), price=Decimal("2"))
    issues = validate_fx_transaction(txn)
    assert any(i.code == FxValidationReasonCode.NON_ZERO_QUANTITY for i in issues)
    assert any(i.code == FxValidationReasonCode.NON_ZERO_PRICE for i in issues)


def test_validate_fx_transaction_requires_distinct_currencies() -> None:
    txn = replace(_base_txn(), buy_currency="USD", sell_currency="USD")
    issues = validate_fx_transaction(txn)
    assert any(i.code == FxValidationReasonCode.SAME_CURRENCY_NOT_ALLOWED for i in issues)


def test_validate_fx_transaction_requires_positive_amounts_and_rate() -> None:
    txn = replace(
        _base_txn(),
        **{
            "buy_amount": Decimal("0"),
            "sell_amount": Decimal("-1"),
            "contract_rate": Decimal("0"),
        },
    )
    issues = validate_fx_transaction(txn)
    assert any(i.code == FxValidationReasonCode.NON_POSITIVE_BUY_AMOUNT for i in issues)
    assert any(i.code == FxValidationReasonCode.NON_POSITIVE_SELL_AMOUNT for i in issues)
    assert any(i.code == FxValidationReasonCode.NON_POSITIVE_CONTRACT_RATE for i in issues)


@pytest.mark.parametrize("trade_fee", [Decimal("0.01"), Decimal("1000000"), Decimal("1095001")])
def test_validate_fx_transaction_rejects_every_non_zero_embedded_fee(
    trade_fee: Decimal,
) -> None:
    txn = replace(_base_txn(), trade_fee=trade_fee)

    issues = validate_fx_transaction(txn)

    assert [issue.code for issue in issues] == [FxValidationReasonCode.NON_ZERO_EMBEDDED_FEE]
    assert issues[0].field == "trade_fee"


@pytest.mark.parametrize("transaction_type", ["FX_SPOT", "FX_FORWARD", "FX_SWAP"])
def test_validate_fx_transaction_applies_embedded_fee_policy_to_every_fx_family(
    transaction_type: str,
) -> None:
    updates: dict[str, object] = {
        "transaction_type": transaction_type,
        "trade_fee": Decimal("1"),
    }
    if transaction_type == "FX_SWAP":
        updates.update(
            swap_event_id="SWAP-001",
            near_leg_group_id="SWAP-001-NEAR",
            far_leg_group_id="SWAP-001-FAR",
        )
    txn = replace(_base_txn(), **updates)

    issues = validate_fx_transaction(txn)

    assert FxValidationReasonCode.NON_ZERO_EMBEDDED_FEE in {issue.code for issue in issues}


def test_validate_fx_transaction_requires_cash_leg_linkage_for_settlement_components() -> None:
    txn = replace(
        _base_txn(),
        **{
            "component_type": "FX_CASH_SETTLEMENT_BUY",
            "fx_cash_leg_role": None,
            "linked_fx_cash_leg_id": None,
        },
    )
    issues = validate_fx_transaction(txn)
    assert any(i.code == FxValidationReasonCode.INVALID_FX_CASH_ROLE for i in issues)
    assert any(i.code == FxValidationReasonCode.MISSING_LINKED_FX_CASH_LEG for i in issues)


def test_validate_fx_transaction_requires_contract_id_for_forwards_and_contract_components() -> (
    None
):
    txn = replace(_base_txn(), fx_contract_id=None)
    issues = validate_fx_transaction(txn)
    assert any(i.code == FxValidationReasonCode.MISSING_FX_CONTRACT_ID for i in issues)


def test_validate_fx_transaction_requires_swap_group_identifiers() -> None:
    txn = replace(
        _base_txn(),
        **{
            "transaction_type": "FX_SWAP",
            "swap_event_id": None,
            "near_leg_group_id": None,
            "far_leg_group_id": None,
        },
    )
    issues = validate_fx_transaction(txn)
    assert any(i.code == FxValidationReasonCode.MISSING_SWAP_GROUP_IDENTIFIER for i in issues)


def test_validate_fx_transaction_rejects_non_distinct_swap_groups() -> None:
    txn = replace(
        _base_txn(),
        **{
            "transaction_type": " fx_swap ",
            "swap_event_id": "FXSWAP-001",
            "near_leg_group_id": "FXSWAP-001-LEG",
            "far_leg_group_id": "FXSWAP-001-LEG",
        },
    )
    issues = validate_fx_transaction(txn)
    assert any(i.code == FxValidationReasonCode.INVALID_SWAP_GROUP_STRUCTURE for i in issues)


def test_validate_fx_transaction_rejects_invalid_policy_modes() -> None:
    txn = replace(
        _base_txn(),
        **{
            "spot_exposure_model": "BAD",
            "fx_realized_pnl_mode": "BAD",
        },
    )
    issues = validate_fx_transaction(txn)
    assert any(i.code == FxValidationReasonCode.INVALID_SPOT_EXPOSURE_MODEL for i in issues)
    assert any(i.code == FxValidationReasonCode.INVALID_REALIZED_PNL_MODE for i in issues)


def test_validate_fx_transaction_rejects_non_zero_capital_pnl_and_total_mismatch() -> None:
    txn = replace(
        _base_txn(),
        **{
            "realized_capital_pnl_local": Decimal("1"),
            "realized_total_pnl_base": Decimal("999"),
        },
    )
    issues = validate_fx_transaction(txn)
    assert any(i.code == FxValidationReasonCode.NON_ZERO_REALIZED_CAPITAL_PNL for i in issues)
    assert any(i.code == FxValidationReasonCode.REALIZED_TOTAL_PNL_MISMATCH for i in issues)


def test_validate_fx_transaction_strict_metadata() -> None:
    txn = replace(
        _base_txn(),
        **{
            "economic_event_id": None,
            "linked_transaction_group_id": None,
            "calculation_policy_id": None,
            "calculation_policy_version": None,
        },
    )
    issues = validate_fx_transaction(txn, strict_metadata=True)
    assert any(i.code == FxValidationReasonCode.MISSING_LINKAGE_IDENTIFIER for i in issues)
    assert any(i.code == FxValidationReasonCode.MISSING_POLICY_METADATA for i in issues)
