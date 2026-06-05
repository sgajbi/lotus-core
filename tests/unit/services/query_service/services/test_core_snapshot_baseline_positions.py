from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace

from src.services.query_service.app.services.core_snapshot_baseline_positions import (
    baseline_position_entries,
)


def _snapshot_row(
    security_id: str = "SEC_A",
    quantity: object = Decimal("3"),
    market_value: object = Decimal("30"),
    market_value_local: object = Decimal("30"),
) -> SimpleNamespace:
    return SimpleNamespace(
        security_id=security_id,
        quantity=quantity,
        market_value=market_value,
        market_value_local=market_value_local,
    )


def _history_row(
    security_id: str = "SEC_BOND",
    quantity: object = Decimal("3"),
    cost_basis: object = Decimal("45"),
    cost_basis_local: object = Decimal("45"),
) -> SimpleNamespace:
    return SimpleNamespace(
        security_id=security_id,
        quantity=quantity,
        cost_basis=cost_basis,
        cost_basis_local=cost_basis_local,
    )


def _instrument(
    security_id: str = "SEC_A",
    currency: str = "USD",
    asset_class: str = "EQUITY",
) -> SimpleNamespace:
    return SimpleNamespace(
        security_id=security_id,
        name=f"{security_id}-name",
        isin=f"{security_id}-isin",
        currency=currency,
        asset_class=asset_class,
        sector="TECHNOLOGY",
        country_of_risk="US",
        issuer_id=f"ISSUER_{security_id}",
        issuer_name=f"{security_id} issuer",
        ultimate_parent_issuer_id=f"PARENT_{security_id}",
        ultimate_parent_issuer_name=f"{security_id} parent",
        liquidity_tier="L2",
    )


def test_baseline_position_entries_normalizes_security_ids_and_sorts() -> None:
    entries = baseline_position_entries(
        rows=[
            (_snapshot_row(" SEC_B "), _instrument("SEC_B"), object()),
            (_snapshot_row(" SEC_A "), _instrument("SEC_A"), object()),
        ],
        use_snapshot=True,
        reporting_fx=Decimal("1"),
        include_cash=True,
        include_zero=True,
    )

    assert list(entries) == ["SEC_A", "SEC_B"]
    assert entries["SEC_A"]["security_id"] == "SEC_A"
    assert entries["SEC_A"]["instrument_name"] == "SEC_A-name"


def test_baseline_position_entries_preserves_blank_optional_market_values() -> None:
    entries = baseline_position_entries(
        rows=[(_snapshot_row("SEC_BLANK", "3", " ", ""), _instrument("SEC_BLANK"), object())],
        use_snapshot=True,
        reporting_fx=Decimal("1"),
        include_cash=True,
        include_zero=True,
    )

    assert entries["SEC_BLANK"]["quantity"] == Decimal("3")
    assert entries["SEC_BLANK"]["market_value_base"] is None
    assert entries["SEC_BLANK"]["market_value_local"] is None


def test_baseline_position_entries_uses_history_cost_basis_and_reporting_fx() -> None:
    entries = baseline_position_entries(
        rows=[(_history_row("SEC_BOND"), _instrument("SEC_BOND", asset_class="BOND"), object())],
        use_snapshot=False,
        reporting_fx=Decimal("1.5"),
        include_cash=True,
        include_zero=True,
    )

    assert entries["SEC_BOND"]["market_value_base"] == Decimal("67.5")
    assert entries["SEC_BOND"]["market_value_local"] == Decimal("45")


def test_baseline_position_entries_filters_cash_and_zero_positions() -> None:
    entries = baseline_position_entries(
        rows=[
            (
                _snapshot_row("SEC_CASH", Decimal("1"), Decimal("1"), Decimal("1")),
                _instrument("SEC_CASH", asset_class=" cash "),
                object(),
            ),
            (
                _snapshot_row("SEC_ZERO", Decimal("0"), Decimal("0"), Decimal("0")),
                _instrument("SEC_ZERO"),
                object(),
            ),
            (
                _snapshot_row("SEC_KEEP", Decimal("1"), Decimal("10"), Decimal("10")),
                _instrument("SEC_KEEP"),
                object(),
            ),
        ],
        use_snapshot=True,
        reporting_fx=Decimal("1"),
        include_cash=False,
        include_zero=False,
    )

    assert list(entries) == ["SEC_KEEP"]
