"""Test realized FX baseline processing and cost-basis effects."""

from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal

import pytest

from src.services.portfolio_transaction_processing_service.app.domain.transaction import (
    BookedTransaction,
)
from src.services.portfolio_transaction_processing_service.app.domain.transaction.fx import (
    UnsupportedFxRealizedPnlModeError,
    build_fx_baseline_processing_update,
    build_fx_processed_transaction,
)


def _fx_transaction(**updates: object) -> BookedTransaction:
    transaction = BookedTransaction(
        transaction_id="FX-BASELINE-001",
        portfolio_id="PORT-FX-1",
        instrument_id="FXC-EURUSD-001",
        security_id="FXC-EURUSD-001",
        transaction_date=datetime(2026, 4, 1, 9, 0, 0, tzinfo=UTC),
        settlement_date=datetime(2026, 7, 1, 0, 0, 0, tzinfo=UTC),
        transaction_type="FX_FORWARD",
        component_type="FX_CONTRACT_CLOSE",
        quantity=Decimal("0"),
        price=Decimal("0"),
        gross_transaction_amount=Decimal("0"),
        trade_currency="USD",
        currency="USD",
        pair_base_currency="EUR",
        pair_quote_currency="USD",
        buy_currency="USD",
        sell_currency="EUR",
        buy_amount=Decimal("1095000"),
        sell_amount=Decimal("1000000"),
        contract_rate=Decimal("1.095"),
        fx_contract_id="FXC-2026-0001",
        fx_realized_pnl_mode="NONE",
    )
    return replace(transaction, **updates)


def test_build_fx_processed_transaction_normalizes_none_realized_pnl_mode() -> None:
    transaction = _fx_transaction(
        fx_realized_pnl_mode=" none ",
        realized_capital_pnl_local=Decimal("10"),
        realized_fx_pnl_local=Decimal("20"),
        realized_total_pnl_local=Decimal("30"),
        realized_capital_pnl_base=Decimal("10"),
        realized_fx_pnl_base=Decimal("20"),
        realized_total_pnl_base=Decimal("30"),
    )

    processed = build_fx_processed_transaction(transaction)

    assert processed.fx_realized_pnl_mode == "NONE"
    assert processed.realized_capital_pnl_local == Decimal("0")
    assert processed.realized_fx_pnl_local == Decimal("0")
    assert processed.realized_total_pnl_local == Decimal("0")
    assert processed.realized_capital_pnl_base == Decimal("0")
    assert processed.realized_fx_pnl_base == Decimal("0")
    assert processed.realized_total_pnl_base == Decimal("0")


def test_build_fx_processed_transaction_normalizes_upstream_provided_mode() -> None:
    transaction = _fx_transaction(
        fx_realized_pnl_mode=" upstream_provided ",
        realized_capital_pnl_local=Decimal("0"),
        realized_fx_pnl_local=Decimal("20"),
        realized_capital_pnl_base=Decimal("0"),
        realized_fx_pnl_base=Decimal("25"),
    )

    processed = build_fx_processed_transaction(transaction)

    assert processed.fx_realized_pnl_mode == "UPSTREAM_PROVIDED"
    assert processed.realized_total_pnl_local == Decimal("20")
    assert processed.realized_total_pnl_base == Decimal("25")


def test_build_fx_processed_transaction_rejects_unsupported_cash_lot_mode() -> None:
    transaction = _fx_transaction(fx_realized_pnl_mode=" cash_lot_cost_method ")

    with pytest.raises(
        UnsupportedFxRealizedPnlModeError,
        match="CASH_LOT_COST_METHOD.*supported modes are NONE and UPSTREAM_PROVIDED",
    ):
        build_fx_processed_transaction(transaction)


def test_baseline_update_preserves_cost_engine_mapping_contract() -> None:
    update = build_fx_baseline_processing_update(
        _fx_transaction(
            fx_realized_pnl_mode="UPSTREAM_PROVIDED",
            gross_cost=Decimal("11"),
            net_cost=Decimal("12"),
            realized_gain_loss=Decimal("13"),
            net_cost_local=Decimal("14"),
            realized_gain_loss_local=Decimal("15"),
            realized_capital_pnl_local=Decimal("16"),
            realized_fx_pnl_local=Decimal("17"),
            realized_capital_pnl_base=Decimal("18"),
            realized_fx_pnl_base=Decimal("19"),
        )
    )

    assert update == {
        "fx_realized_pnl_mode": "UPSTREAM_PROVIDED",
        "gross_cost": Decimal("11"),
        "net_cost": Decimal("12"),
        "realized_gain_loss": Decimal("13"),
        "net_cost_local": Decimal("14"),
        "realized_gain_loss_local": Decimal("15"),
        "realized_capital_pnl_local": Decimal("16"),
        "realized_fx_pnl_local": Decimal("17"),
        "realized_total_pnl_local": Decimal("33"),
        "realized_capital_pnl_base": Decimal("18"),
        "realized_fx_pnl_base": Decimal("19"),
        "realized_total_pnl_base": Decimal("37"),
    }


@pytest.mark.parametrize(
    "field_name",
    [
        "realized_capital_pnl_local",
        "realized_fx_pnl_local",
        "realized_total_pnl_local",
        "realized_capital_pnl_base",
        "realized_fx_pnl_base",
        "realized_total_pnl_base",
    ],
)
def test_v2_receipt_distinguishes_absent_from_explicit_zero_before_defaulting(
    field_name: str,
) -> None:
    absent = _fx_transaction(fx_realized_pnl_mode="UPSTREAM_PROVIDED")
    explicit = replace(absent, **{field_name: Decimal("0")})
    absent_output = build_fx_processed_transaction(absent)
    explicit_output = build_fx_processed_transaction(explicit)

    assert replace(absent_output, calculation_lineage=None) == replace(
        explicit_output, calculation_lineage=None
    )
    assert absent_output.calculation_lineage is not None
    assert explicit_output.calculation_lineage is not None
    assert absent_output.calculation_lineage.algorithm_version == 2
    assert (
        absent_output.calculation_lineage.input_content_hash
        != explicit_output.calculation_lineage.input_content_hash
    )


def test_v2_receipt_preserves_original_signed_values_even_when_none_mode_discards_them() -> None:
    positive = build_fx_processed_transaction(_fx_transaction(realized_fx_pnl_local=Decimal("12")))
    negative = build_fx_processed_transaction(_fx_transaction(realized_fx_pnl_local=Decimal("-12")))
    assert replace(positive, calculation_lineage=None) == replace(
        negative, calculation_lineage=None
    )
    assert positive.calculation_lineage is not None
    assert negative.calculation_lineage is not None
    assert (
        positive.calculation_lineage.input_content_hash
        != negative.calculation_lineage.input_content_hash
    )
