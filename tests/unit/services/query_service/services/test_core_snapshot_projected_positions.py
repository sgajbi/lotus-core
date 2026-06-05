from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace

import pytest

from src.services.query_service.app.services.core_snapshot_projected_positions import (
    apply_baseline_projected_values,
    apply_projected_position_changes,
    baseline_projected_positions,
    change_quantity_effect,
    filtered_projected_positions,
    missing_projected_security_ids,
    new_projected_position,
)


def _instrument(
    security_id: str = "SEC_NEW",
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


def test_baseline_projected_positions_copies_entries_and_tracks_baseline_quantity() -> None:
    baseline = {
        "SEC_A": {
            "security_id": "SEC_A",
            "quantity": Decimal("4"),
            "market_value_base": Decimal("40"),
        }
    }

    projected = baseline_projected_positions(baseline)

    assert projected["SEC_A"]["baseline_quantity"] == Decimal("4")
    assert projected["SEC_A"] is not baseline["SEC_A"]


def test_missing_projected_security_ids_returns_only_new_changed_ids() -> None:
    missing = missing_projected_security_ids(
        {"SEC_EXISTING": {"security_id": "SEC_EXISTING"}},
        [
            ("SEC_EXISTING", object()),
            ("SEC_NEW_A", object()),
            ("SEC_NEW_B", object()),
            ("SEC_NEW_A", object()),
        ],
    )

    assert sorted(missing) == ["SEC_NEW_A", "SEC_NEW_B"]


def test_new_projected_position_builds_zero_quantity_instrument_payload() -> None:
    position = new_projected_position("SEC_NEW", _instrument("SEC_NEW", "EUR", "BOND"))

    assert position["security_id"] == "SEC_NEW"
    assert position["quantity"] == Decimal("0")
    assert position["baseline_quantity"] == Decimal("0")
    assert position["market_value_base"] == Decimal("0")
    assert position["currency"] == "EUR"
    assert position["asset_class"] == "BOND"
    assert position["liquidity_tier"] == "L2"


def test_apply_projected_position_changes_applies_transaction_quantity_effects() -> None:
    projected = {
        "SEC_A": {"security_id": "SEC_A", "quantity": Decimal("10")},
        "SEC_B": {"security_id": "SEC_B", "quantity": Decimal("5")},
    }

    apply_projected_position_changes(
        projected,
        [
            (
                "SEC_A",
                SimpleNamespace(transaction_type="BUY", quantity=Decimal("2"), amount=None),
            ),
            (
                "SEC_B",
                SimpleNamespace(transaction_type="SELL", quantity=Decimal("3"), amount=None),
            ),
        ],
    )

    assert projected["SEC_A"]["quantity"] == Decimal("12")
    assert projected["SEC_B"]["quantity"] == Decimal("2")


def test_apply_baseline_projected_values_reuses_baseline_unit_values() -> None:
    projected = {
        "SEC_A": {
            "security_id": "SEC_A",
            "quantity": Decimal("6"),
            "baseline_quantity": Decimal("3"),
            "market_value_base": Decimal("30"),
            "market_value_local": Decimal("24"),
            "asset_class": "EQUITY",
        }
    }

    price_required = apply_baseline_projected_values(
        projected,
        include_cash=True,
        include_zero=True,
    )

    assert price_required == {}
    assert projected["SEC_A"]["market_value_base"] == Decimal("60")
    assert projected["SEC_A"]["market_value_local"] == Decimal("48")


def test_apply_baseline_projected_values_tracks_positive_new_positions_for_pricing() -> None:
    projected = {
        "SEC_NEW": {
            "security_id": "SEC_NEW",
            "quantity": Decimal("2"),
            "baseline_quantity": Decimal("0"),
            "market_value_base": Decimal("0"),
            "market_value_local": Decimal("0"),
            "asset_class": "EQUITY",
        },
        "SEC_NEG": {
            "security_id": "SEC_NEG",
            "quantity": Decimal("-1"),
            "baseline_quantity": Decimal("0"),
            "market_value_base": Decimal("9"),
            "market_value_local": Decimal("9"),
            "asset_class": "EQUITY",
        },
    }

    price_required = apply_baseline_projected_values(
        projected,
        include_cash=True,
        include_zero=True,
    )

    assert price_required == {"SEC_NEW": (projected["SEC_NEW"], Decimal("2"))}
    assert projected["SEC_NEG"]["market_value_base"] == Decimal("0")
    assert projected["SEC_NEG"]["market_value_local"] == Decimal("0")


def test_filtered_projected_positions_applies_cash_and_zero_filters() -> None:
    projected = {
        "SEC_CASH": {
            "security_id": "SEC_CASH",
            "quantity": Decimal("1"),
            "asset_class": " cash ",
        },
        "SEC_ZERO": {
            "security_id": "SEC_ZERO",
            "quantity": Decimal("0"),
            "asset_class": "EQUITY",
        },
        "SEC_KEEP": {
            "security_id": "SEC_KEEP",
            "quantity": Decimal("1"),
            "asset_class": "EQUITY",
        },
    }

    filtered = filtered_projected_positions(
        projected,
        include_cash=False,
        include_zero=False,
    )

    assert list(filtered) == ["SEC_KEEP"]


@pytest.mark.parametrize(
    ("txn_type", "quantity", "amount", "expected"),
    [
        ("BUY", Decimal("2"), None, Decimal("2")),
        ("SELL", Decimal("2"), None, Decimal("-2")),
        ("TRANSFER_IN", Decimal("5"), Decimal("9"), Decimal("5")),
        ("TRANSFER_OUT", Decimal("3"), Decimal("9"), Decimal("-3")),
        ("DEPOSIT", None, Decimal("7"), Decimal("7")),
        ("WITHDRAWAL", None, Decimal("7"), Decimal("-7")),
        ("FEE", None, Decimal("7"), Decimal("-7")),
        ("TAX", None, Decimal("7"), Decimal("-7")),
        ("UNKNOWN", Decimal("3"), None, Decimal("0")),
    ],
)
def test_change_quantity_effect_rules(txn_type, quantity, amount, expected) -> None:
    change = SimpleNamespace(transaction_type=txn_type, quantity=quantity, amount=amount)

    assert change_quantity_effect(change) == expected
