from decimal import Decimal

import pytest
from cost_engine.domain.corporate_action_cash_economics import (
    CorporateActionCashEconomicsError,
    calculate_corporate_action_cash_economics,
)


def _calculate(**overrides: object):
    values = {
        "gross_proceeds_local": Decimal("250"),
        "fees_local": Decimal("0"),
        "allocated_cost_basis_local": Decimal("50"),
        "allocated_cost_basis_base": Decimal("50"),
        "local_currency": "USD",
        "base_currency": "USD",
        "transaction_fx_rate": Decimal("1"),
    }
    values.update(overrides)
    return calculate_corporate_action_cash_economics(**values)


def test_same_currency_cash_consideration_realizes_capital_gain() -> None:
    economics = _calculate()

    assert economics.net_proceeds_local == Decimal("250")
    assert economics.allocated_cost_basis_local == Decimal("50")
    assert economics.realized_capital_pnl_local == Decimal("200")
    assert economics.realized_fx_pnl_local == Decimal("0")
    assert economics.realized_total_pnl_local == Decimal("200")
    assert economics.realized_capital_pnl_base == Decimal("200")
    assert economics.realized_fx_pnl_base == Decimal("0")
    assert economics.realized_total_pnl_base == Decimal("200")


def test_cash_consideration_can_realize_loss_and_deduct_fees() -> None:
    economics = _calculate(
        gross_proceeds_local=Decimal("45"),
        fees_local=Decimal("5"),
        allocated_cost_basis_local=Decimal("50"),
        allocated_cost_basis_base=Decimal("50"),
    )

    assert economics.net_proceeds_local == Decimal("40")
    assert economics.realized_total_pnl_local == Decimal("-10")
    assert economics.realized_total_pnl_base == Decimal("-10")


def test_cross_currency_cash_consideration_requires_and_preserves_explicit_pnl_split() -> None:
    economics = _calculate(
        allocated_cost_basis_base=Decimal("60"),
        base_currency="SGD",
        transaction_fx_rate=Decimal("1.4"),
        realized_capital_pnl_local=Decimal("190"),
        realized_fx_pnl_local=Decimal("10"),
        realized_capital_pnl_base=Decimal("270"),
        realized_fx_pnl_base=Decimal("20"),
        realized_total_pnl_local=Decimal("200"),
        realized_total_pnl_base=Decimal("290"),
    )

    assert economics.net_proceeds_base == Decimal("350.0")
    assert economics.realized_capital_pnl_base == Decimal("270")
    assert economics.realized_fx_pnl_base == Decimal("20")
    assert economics.realized_total_pnl_base == Decimal("290.0")


@pytest.mark.parametrize(
    ("field_name", "overrides", "message"),
    [
        (
            "allocated_cost_basis_local",
            {"allocated_cost_basis_local": None},
            "allocated_cost_basis_local is required",
        ),
        (
            "allocated_cost_basis_base",
            {"allocated_cost_basis_base": None},
            "allocated_cost_basis_base is required",
        ),
        (
            "allocated_cost_basis_local",
            {"allocated_cost_basis_local": Decimal("-0.01")},
            "allocated_cost_basis_local must be greater than or equal to 0",
        ),
        (
            "fees_local",
            {"fees_local": Decimal("251")},
            "fees_local must not exceed gross_proceeds_local",
        ),
        (
            "allocated_cost_basis_base",
            {"allocated_cost_basis_base": Decimal("49")},
            "allocated_cost_basis_base must equal allocated_cost_basis_local",
        ),
        (
            "realized_fx_pnl_local",
            {"realized_fx_pnl_local": Decimal("1")},
            "same-currency realized P&L local components",
        ),
        (
            "cross_currency_components",
            {
                "base_currency": "SGD",
                "transaction_fx_rate": Decimal("1.4"),
                "allocated_cost_basis_base": Decimal("60"),
            },
            "cross-currency realized capital and FX P&L local components are required",
        ),
        (
            "cross_currency_sum",
            {
                "base_currency": "SGD",
                "transaction_fx_rate": Decimal("1.4"),
                "allocated_cost_basis_base": Decimal("60"),
                "realized_capital_pnl_local": Decimal("190"),
                "realized_fx_pnl_local": Decimal("9"),
                "realized_capital_pnl_base": Decimal("270"),
                "realized_fx_pnl_base": Decimal("20"),
            },
            "cross-currency realized capital and FX P&L local components must reconcile",
        ),
        (
            "realized_total_pnl_base",
            {"realized_total_pnl_base": Decimal("199")},
            "realized_total_pnl_base must reconcile",
        ),
    ],
)
def test_cash_consideration_rejects_incomplete_or_inconsistent_economics(
    field_name: str,
    overrides: dict[str, object],
    message: str,
) -> None:
    del field_name

    with pytest.raises(CorporateActionCashEconomicsError, match=message):
        _calculate(**overrides)
