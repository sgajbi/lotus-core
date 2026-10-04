"""Fresh source admission is independent of historical receipt reconstruction."""

from decimal import Decimal

import pytest
from portfolio_common.domain.transaction.fx_source_admission import (
    FX_SOURCE_ADMISSION_TYPES,
    missing_fx_upstream_source_fields,
)


@pytest.mark.parametrize("transaction_type", sorted(FX_SOURCE_ADMISSION_TYPES))
@pytest.mark.parametrize(
    "component_type", [None, "FX_CONTRACT_CLOSE", "FX_CASH_SETTLEMENT_SELL", "BAD"]
)
@pytest.mark.parametrize(
    ("local", "base", "expected"),
    [
        (None, None, ("realized_fx_pnl_local", "realized_fx_pnl_base")),
        (Decimal(0), None, ("realized_fx_pnl_base",)),
        (None, Decimal(0), ("realized_fx_pnl_local",)),
        (Decimal(0), Decimal(0), ()),
        (Decimal("-12"), Decimal("15"), ()),
    ],
)
def test_applicable_source_requires_each_basis_without_coercion(
    transaction_type: str,
    component_type: str | None,
    local: Decimal | None,
    base: Decimal | None,
    expected: tuple[str, ...],
) -> None:
    assert (
        missing_fx_upstream_source_fields(
            transaction_type=f" {transaction_type.lower()} ",
            component_type=component_type,
            fx_realized_pnl_mode=" upstream_provided ",
            realized_fx_pnl_local=local,
            realized_fx_pnl_base=base,
        )
        == expected
    )


@pytest.mark.parametrize(
    ("transaction_type", "component_type", "mode"),
    [
        ("BUY", "FX_CONTRACT_CLOSE", "UPSTREAM_PROVIDED"),
        ("FX_CASH_SETTLEMENT_BUY", "FX_CASH_SETTLEMENT_BUY", "UPSTREAM_PROVIDED"),
        ("FX_FORWARD", " fx_contract_open ", "UPSTREAM_PROVIDED"),
        ("FX_FORWARD", "FX_CONTRACT_CLOSE", "NONE"),
        ("FX_FORWARD", "FX_CONTRACT_CLOSE", None),
        ("FX_FORWARD", "FX_CONTRACT_CLOSE", "CASH_LOT_COST_METHOD"),
        ("FX_FORWARD", "FX_CONTRACT_CLOSE", "UNSUPPORTED"),
    ],
)
def test_rule_does_not_replace_separate_business_validation(
    transaction_type: str, component_type: str, mode: str | None
) -> None:
    assert (
        missing_fx_upstream_source_fields(
            transaction_type=transaction_type,
            component_type=component_type,
            fx_realized_pnl_mode=mode,
            realized_fx_pnl_local=None,
            realized_fx_pnl_base=None,
        )
        == ()
    )
