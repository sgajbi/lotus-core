"""Test fixed-income redemption economics and fail-closed invariants."""

from dataclasses import replace
from decimal import Decimal, localcontext

import pytest
from portfolio_common.domain.calculation_lineage import calculation_lineage_binds_output

from src.services.portfolio_transaction_processing_service.app.domain.transaction import redemption

RedemptionCalculationError = redemption.RedemptionCalculationError
RedemptionCalculationReasonCode = redemption.RedemptionCalculationReasonCode
RedemptionTerms = redemption.RedemptionTerms
calculate_redemption_economics = redemption.calculate_redemption_economics


def _terms(**changes: object) -> RedemptionTerms:
    base = RedemptionTerms(
        transaction_type="MATURITY_REDEMPTION",
        position_quantity=Decimal("100"),
        redeemed_quantity=Decimal("100"),
        redemption_price=Decimal("100"),
        principal_proceeds_local=Decimal("10000"),
        accrued_interest_proceeds_local=Decimal("50"),
        embedded_fee_amount_local=Decimal("2"),
        embedded_tax_amount_local=Decimal("3"),
        allocated_cost_basis_local=Decimal("9800"),
        allocated_cost_basis_base=Decimal("7350"),
        fx_rate_to_base=Decimal("0.75"),
    )
    return replace(base, **changes)


def test_maturity_redemption_separates_principal_interest_and_capital_pnl() -> None:
    result = calculate_redemption_economics(_terms())

    assert result.redeemed_quantity == Decimal("100.0000000000")
    assert result.remaining_quantity == Decimal("0E-10")
    assert result.principal_proceeds_local == Decimal("10000.0000000000")
    assert result.accrued_interest_proceeds_local == Decimal("50")
    assert result.total_cash_proceeds_local == Decimal("10045.0000000000")
    assert result.principal_proceeds_base == Decimal("7500.0000000000")
    assert result.realized_capital_pnl_local == Decimal("200.0000000000")
    assert result.realized_capital_pnl_base == Decimal("150.0000000000")


def test_partial_redemption_resolves_factor_authority_deterministically() -> None:
    result = calculate_redemption_economics(
        _terms(
            transaction_type=" partial_redemption ",
            redeemed_quantity=None,
            old_factor=Decimal("1.0"),
            new_factor=Decimal("0.75"),
            redemption_price=Decimal("100"),
            principal_proceeds_local=None,
            accrued_interest_proceeds_local=Decimal(0),
            embedded_fee_amount_local=Decimal(0),
            embedded_tax_amount_local=Decimal(0),
            allocated_cost_basis_local=Decimal("2450"),
            allocated_cost_basis_base=Decimal("1837.5"),
        )
    )

    assert result.redeemed_quantity == Decimal("25.0000000000")
    assert result.remaining_quantity == Decimal("75.0000000000")
    assert result.principal_proceeds_local == Decimal("2500.0000000000")
    assert result.realized_capital_pnl_local == Decimal("50.0000000000")


def test_factor_quantity_is_independent_of_ambient_decimal_precision() -> None:
    terms = _terms(
        transaction_type="PARTIAL_REDEMPTION",
        redeemed_quantity=None,
        old_factor=Decimal("3"),
        new_factor=Decimal("2"),
        principal_proceeds_local=None,
    )

    with localcontext() as context:
        context.prec = 6
        result = calculate_redemption_economics(terms)

    assert result.redeemed_quantity == Decimal("33.3333333333")


def test_explicit_and_factor_quantity_must_reconcile() -> None:
    with pytest.raises(RedemptionCalculationError) as raised:
        calculate_redemption_economics(
            _terms(
                transaction_type="PARTIAL_REDEMPTION",
                redeemed_quantity=Decimal("24"),
                old_factor=Decimal("1"),
                new_factor=Decimal("0.75"),
            )
        )

    assert raised.value.code is RedemptionCalculationReasonCode.QUANTITY_AUTHORITY_MISMATCH


@pytest.mark.parametrize("transaction_type", ["MATURITY_REDEMPTION", "CALL_REDEMPTION"])
def test_full_redemption_types_must_close_the_position(transaction_type: str) -> None:
    with pytest.raises(RedemptionCalculationError) as raised:
        calculate_redemption_economics(
            _terms(transaction_type=transaction_type, redeemed_quantity=Decimal("99"))
        )

    assert raised.value.code is RedemptionCalculationReasonCode.FULL_REDEMPTION_QUANTITY_MISMATCH


def test_partial_redemption_must_leave_a_position() -> None:
    with pytest.raises(RedemptionCalculationError) as raised:
        calculate_redemption_economics(_terms(transaction_type="PARTIAL_REDEMPTION"))

    assert raised.value.code is RedemptionCalculationReasonCode.PARTIAL_REDEMPTION_CLOSES_POSITION


def test_principal_authority_must_reconcile_to_quantity_times_price() -> None:
    with pytest.raises(RedemptionCalculationError) as raised:
        calculate_redemption_economics(_terms(principal_proceeds_local=Decimal("9999")))

    assert raised.value.code is RedemptionCalculationReasonCode.PRINCIPAL_PROCEEDS_MISMATCH


def test_embedded_deductions_cannot_make_total_cash_negative() -> None:
    with pytest.raises(RedemptionCalculationError) as raised:
        calculate_redemption_economics(
            _terms(
                accrued_interest_proceeds_local=Decimal(0),
                embedded_fee_amount_local=Decimal("10001"),
                embedded_tax_amount_local=Decimal(0),
            )
        )

    assert raised.value.code is RedemptionCalculationReasonCode.NEGATIVE_TOTAL_CASH_PROCEEDS


@pytest.mark.parametrize(
    ("changes", "expected_code"),
    [
        ({"transaction_type": "SELL"}, RedemptionCalculationReasonCode.INVALID_TRANSACTION_TYPE),
        (
            {"redeemed_quantity": None},
            RedemptionCalculationReasonCode.MISSING_QUANTITY_AUTHORITY,
        ),
        (
            {"old_factor": Decimal("1"), "new_factor": None},
            RedemptionCalculationReasonCode.INCOMPLETE_FACTOR_AUTHORITY,
        ),
        (
            {"old_factor": Decimal("1"), "new_factor": Decimal("1")},
            RedemptionCalculationReasonCode.INVALID_FACTOR_TRANSITION,
        ),
        (
            {"fx_rate_to_base": Decimal(0)},
            RedemptionCalculationReasonCode.NON_POSITIVE_FX_RATE,
        ),
        (
            {"reconciliation_tolerance": Decimal("-0.01")},
            RedemptionCalculationReasonCode.INVALID_TOLERANCE,
        ),
    ],
)
def test_invalid_redemption_inputs_fail_with_stable_reason_codes(
    changes: dict[str, object],
    expected_code: RedemptionCalculationReasonCode,
) -> None:
    with pytest.raises(RedemptionCalculationError) as raised:
        calculate_redemption_economics(_terms(**changes))

    assert raised.value.code is expected_code


def test_calculation_lineage_binds_every_redemption_output() -> None:
    result = calculate_redemption_economics(_terms())

    assert calculation_lineage_binds_output(
        result.calculation_lineage,
        output_payload={
            "accrued_interest_proceeds_local": result.accrued_interest_proceeds_local,
            "derived_principal_proceeds_local": result.derived_principal_proceeds_local,
            "principal_proceeds_base": result.principal_proceeds_base,
            "principal_proceeds_local": result.principal_proceeds_local,
            "realized_capital_pnl_base": result.realized_capital_pnl_base,
            "realized_capital_pnl_local": result.realized_capital_pnl_local,
            "redeemed_quantity": result.redeemed_quantity,
            "remaining_quantity": result.remaining_quantity,
            "total_cash_proceeds_local": result.total_cash_proceeds_local,
        },
    )
