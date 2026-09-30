"""Verify generated settlement cash-leg economics and lineage."""

from dataclasses import replace
from datetime import datetime
from decimal import Decimal

import pytest

from src.services.portfolio_transaction_processing_service.app.domain.transaction import (
    BookedTransaction,
    GeneratedCashLegError,
    SettlementCashRejectionReasonCode,
    SettlementCashValidationError,
    build_generated_settlement_cash_leg,
    should_generate_settlement_cash_leg,
)


def _dividend_transaction() -> BookedTransaction:
    return BookedTransaction(
        transaction_id="DIV-001",
        portfolio_id="PORT-001",
        tenant_id="tenant-test",
        instrument_id="SEC-AAA",
        security_id="SEC-AAA",
        transaction_date=datetime(2026, 3, 5, 10, 0, 0),
        settlement_date=datetime(2026, 3, 6, 10, 0, 0),
        transaction_type="DIVIDEND",
        quantity=Decimal(0),
        price=Decimal(0),
        gross_transaction_amount=Decimal("100.00"),
        trade_currency="USD",
        currency="USD",
        trade_fee=Decimal("2.00"),
        cash_entry_mode="AUTO_GENERATE",
        settlement_cash_account_id="CASH-ACC-USD-001",
        settlement_cash_instrument_id="CASH-USD",
    )


def test_generation_requires_explicit_cash_entry_mode_and_settlement_account() -> None:
    assert not should_generate_settlement_cash_leg(
        replace(_dividend_transaction(), cash_entry_mode=None)
    )
    assert not should_generate_settlement_cash_leg(
        replace(_dividend_transaction(), settlement_cash_account_id=None)
    )


@pytest.mark.parametrize(
    ("transaction_type", "gross_amount", "fee", "direction", "reason", "amount"),
    [
        ("BUY", "100.00", "2.00", "OUTFLOW", "BUY_SETTLEMENT", "102.00"),
        ("SELL", "100.00", "2.00", "INFLOW", "SELL_SETTLEMENT", "98.00"),
        ("DIVIDEND", "100.00", "2.00", "INFLOW", "DIVIDEND_SETTLEMENT", "98.00"),
    ],
)
def test_generated_cash_leg_preserves_trade_and_income_economics(
    transaction_type: str,
    gross_amount: str,
    fee: str,
    direction: str,
    reason: str,
    amount: str,
) -> None:
    transaction = replace(
        _dividend_transaction(),
        transaction_type=f" {transaction_type.lower()} ",
        gross_transaction_amount=Decimal(gross_amount),
        trade_fee=Decimal(fee),
    )

    cash_leg = build_generated_settlement_cash_leg(transaction)

    assert cash_leg.transaction_type == "ADJUSTMENT"
    assert cash_leg.transaction_id == "DIV-001-CASHLEG"
    assert cash_leg.tenant_id == "tenant-test"
    assert cash_leg.originating_transaction_id == "DIV-001"
    assert cash_leg.originating_transaction_type == transaction_type
    assert cash_leg.movement_direction == direction
    assert cash_leg.adjustment_reason == reason
    assert cash_leg.gross_transaction_amount == Decimal(amount)
    assert cash_leg.instrument_id == "CASH-USD"


@pytest.mark.parametrize(
    "transaction_type",
    ["MATURITY_REDEMPTION", "CALL_REDEMPTION", "PARTIAL_REDEMPTION"],
)
def test_generated_redemption_cash_leg_separates_principal_interest_and_deductions(
    transaction_type: str,
) -> None:
    transaction = replace(
        _dividend_transaction(),
        transaction_type=transaction_type,
        gross_transaction_amount=Decimal("999"),
        principal_proceeds_local=Decimal("100"),
        accrued_interest_proceeds_local=Decimal("10"),
        embedded_fee_amount_local=Decimal("2"),
        embedded_tax_amount_local=Decimal("3"),
        trade_fee=Decimal("1"),
    )

    cash_leg = build_generated_settlement_cash_leg(transaction)

    assert cash_leg.gross_transaction_amount == Decimal("104")
    assert cash_leg.movement_direction == "INFLOW"
    assert cash_leg.adjustment_reason == "REDEMPTION_SETTLEMENT"
    assert cash_leg.originating_transaction_type == transaction_type


def test_generated_redemption_cash_leg_omits_exactly_exhausted_proceeds() -> None:
    transaction = replace(
        _dividend_transaction(),
        transaction_type="MATURITY_REDEMPTION",
        principal_proceeds_local=Decimal("5"),
        embedded_tax_amount_local=Decimal("4"),
        trade_fee=Decimal("1"),
    )

    assert not should_generate_settlement_cash_leg(transaction)
    with pytest.raises(GeneratedCashLegError):
        build_generated_settlement_cash_leg(transaction)


@pytest.mark.parametrize(
    "transaction_type",
    ["MATURITY_REDEMPTION", "CALL_REDEMPTION", "PARTIAL_REDEMPTION"],
)
def test_zero_cash_redemption_does_not_generate_adjustment_leg(
    transaction_type: str,
) -> None:
    transaction = replace(
        _dividend_transaction(),
        transaction_type=transaction_type,
        quantity=Decimal("100"),
        price=Decimal(0),
        gross_transaction_amount=Decimal(0),
        principal_proceeds_local=Decimal(0),
        accrued_interest_proceeds_local=Decimal(0),
        embedded_fee_amount_local=Decimal(0),
        embedded_tax_amount_local=Decimal(0),
        trade_fee=Decimal(0),
    )

    assert not should_generate_settlement_cash_leg(transaction)
    with pytest.raises(GeneratedCashLegError):
        build_generated_settlement_cash_leg(transaction)


@pytest.mark.parametrize("net_interest_amount", [None, Decimal("20.00")])
def test_generated_interest_cash_leg_is_invariant_to_explicit_net_interest(
    net_interest_amount: Decimal | None,
) -> None:
    transaction = replace(
        _dividend_transaction(),
        transaction_type=" interest ",
        gross_transaction_amount=Decimal("25.00"),
        trade_fee=Decimal("1.00"),
        interest_direction=" expense ",
        withholding_tax_amount=Decimal("3.00"),
        other_interest_deductions_amount=Decimal("2.00"),
        net_interest_amount=net_interest_amount,
    )

    cash_leg = build_generated_settlement_cash_leg(transaction)

    assert cash_leg.originating_transaction_type == "INTEREST"
    assert cash_leg.movement_direction == "OUTFLOW"
    assert cash_leg.adjustment_reason == "INTEREST_CHARGE_SETTLEMENT"
    assert cash_leg.gross_transaction_amount == Decimal("21.00")


@pytest.mark.parametrize("net_interest_amount", [None, Decimal("20.50")])
def test_generated_interest_income_cash_leg_is_invariant_to_explicit_net_interest(
    net_interest_amount: Decimal | None,
) -> None:
    transaction = replace(
        _dividend_transaction(),
        transaction_type="INTEREST",
        gross_transaction_amount=Decimal("20.50"),
        net_interest_amount=net_interest_amount,
    )

    assert build_generated_settlement_cash_leg(transaction).gross_transaction_amount == Decimal(
        "18.50"
    )


def test_generated_cash_leg_preserves_upstream_linkage_and_policy() -> None:
    transaction = replace(
        _dividend_transaction(),
        economic_event_id="EVENT-UPSTREAM",
        linked_transaction_group_id="GROUP-UPSTREAM",
        calculation_policy_id="POLICY-UPSTREAM",
        calculation_policy_version="2.0.0",
    )

    cash_leg = build_generated_settlement_cash_leg(transaction)

    assert cash_leg.economic_event_id == "EVENT-UPSTREAM"
    assert cash_leg.linked_transaction_group_id == "GROUP-UPSTREAM"
    assert cash_leg.calculation_policy_id == "POLICY-UPSTREAM"
    assert cash_leg.calculation_policy_version == "2.0.0"


def test_generated_cash_leg_preserves_source_booked_fx_rate() -> None:
    cash_leg = build_generated_settlement_cash_leg(
        replace(_dividend_transaction(), transaction_fx_rate=Decimal("2.0"))
    )

    assert cash_leg.transaction_fx_rate == Decimal("2.0")
    assert cash_leg.net_cost_local == Decimal("98.00")
    assert cash_leg.net_cost == Decimal("196.000")
    assert cash_leg.gross_cost == Decimal("196.000")


def test_generated_cash_leg_normalizes_boundary_precision() -> None:
    cash_leg = build_generated_settlement_cash_leg(
        replace(
            _dividend_transaction(),
            gross_transaction_amount=Decimal("1.1234567890"),
            trade_fee=Decimal(0),
            transaction_fx_rate=Decimal("1.1234567890"),
            transaction_fx_rate_origin="SOURCE_BOOKED",
        )
    )

    assert cash_leg.net_cost_local == Decimal("1.1234567890")
    assert cash_leg.net_cost == Decimal("1.2621551568")
    assert cash_leg.gross_cost == Decimal("1.2621551568")


def test_generated_cash_leg_leaves_absent_fx_for_settlement_date_derivation() -> None:
    cash_leg = build_generated_settlement_cash_leg(
        replace(_dividend_transaction(), transaction_fx_rate=None)
    )

    assert cash_leg.transaction_fx_rate is None


def test_generated_cash_leg_uses_component_fee_precedence() -> None:
    transaction = replace(
        _dividend_transaction(),
        transaction_type="SELL",
        trade_fee=Decimal("99.00"),
        brokerage=Decimal("1.25"),
        stamp_duty=Decimal("0.75"),
    )

    cash_leg = build_generated_settlement_cash_leg(transaction)

    assert cash_leg.gross_transaction_amount == Decimal("98.00")
    assert cash_leg.movement_direction == "INFLOW"


def test_generated_dividend_cash_leg_uses_net_withholding_proceeds() -> None:
    cash_leg = build_generated_settlement_cash_leg(
        replace(
            _dividend_transaction(),
            withholding_tax_amount=Decimal("12.30"),
            trade_fee=Decimal("0.70"),
        )
    )

    assert cash_leg.gross_transaction_amount == Decimal("87.00")
    assert cash_leg.movement_direction == "INFLOW"
    assert cash_leg.adjustment_reason == "DIVIDEND_SETTLEMENT"


def test_generated_cash_lineage_distinguishes_equal_net_source_economics_and_mapping() -> None:
    withholding_case = build_generated_settlement_cash_leg(
        replace(
            _dividend_transaction(),
            withholding_tax_amount=Decimal("10"),
            trade_fee=Decimal(0),
        )
    )
    fee_case = build_generated_settlement_cash_leg(
        replace(
            _dividend_transaction(),
            withholding_tax_amount=Decimal(0),
            trade_fee=Decimal("10"),
        )
    )
    remapped_case = build_generated_settlement_cash_leg(
        replace(
            _dividend_transaction(),
            withholding_tax_amount=Decimal("10"),
            trade_fee=Decimal(0),
            settlement_cash_instrument_id="CASH-USD-SECONDARY",
        )
    )

    assert withholding_case.gross_transaction_amount == Decimal("90")
    assert fee_case.gross_transaction_amount == Decimal("90")
    assert remapped_case.gross_transaction_amount == Decimal("90")
    assert withholding_case.calculation_lineage is not None
    assert fee_case.calculation_lineage is not None
    assert remapped_case.calculation_lineage is not None
    assert withholding_case.calculation_lineage.input_content_hash != (
        fee_case.calculation_lineage.input_content_hash
    )
    assert withholding_case.calculation_lineage.input_content_hash != (
        remapped_case.calculation_lineage.input_content_hash
    )


@pytest.mark.parametrize("fee", [Decimal("100.00"), Decimal("100.01")])
def test_generated_cash_leg_rejects_non_positive_net_settlement(fee: Decimal) -> None:
    transaction = replace(
        _dividend_transaction(),
        transaction_type="SELL",
        trade_fee=fee,
    )

    with pytest.raises(SettlementCashValidationError) as raised:
        build_generated_settlement_cash_leg(transaction)

    assert raised.value.reason_code is (
        SettlementCashRejectionReasonCode.SELL_NON_POSITIVE_NET_SETTLEMENT
    )


def test_generated_cash_leg_rejects_ineligible_transaction() -> None:
    transaction = replace(
        _dividend_transaction(),
        transaction_type="DEPOSIT",
    )

    with pytest.raises(GeneratedCashLegError):
        build_generated_settlement_cash_leg(transaction)
