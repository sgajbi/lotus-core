from datetime import date

import pytest
from portfolio_common.reconstruction_identity import (
    PortfolioReconstructionScope,
    build_portfolio_snapshot_id,
)


def _scope(**overrides) -> PortfolioReconstructionScope:
    values = {
        "portfolio_id": "PORT_001",
        "as_of_date": date(2026, 2, 27),
        "valuation_date": date(2026, 2, 27),
        "position_epoch": 7,
        "cashflow_epoch": 5,
        "transaction_window_start": date(2026, 1, 1),
        "transaction_window_end": date(2026, 2, 27),
        "source_data_products": (
            "TransactionLedgerWindow",
            "HoldingsAsOf",
            "MarketDataWindow",
        ),
        "policy_version": "tenant-default-v1",
    }
    values.update(overrides)
    return PortfolioReconstructionScope(**values)


def test_portfolio_snapshot_id_is_deterministic_for_same_scope() -> None:
    first = build_portfolio_snapshot_id(_scope())
    second = build_portfolio_snapshot_id(_scope())

    assert first == second
    assert first.startswith("pss_")
    assert len(first) == len("pss_") + 32


def test_portfolio_snapshot_id_ignores_source_product_order_and_duplicates() -> None:
    first = build_portfolio_snapshot_id(
        _scope(source_data_products=("MarketDataWindow", "HoldingsAsOf", "HoldingsAsOf"))
    )
    second = build_portfolio_snapshot_id(
        _scope(source_data_products=("HoldingsAsOf", "MarketDataWindow"))
    )

    assert first == second


@pytest.mark.parametrize(
    ("field_name", "value"),
    [
        ("restatement_version", "restatement_0002"),
        ("portfolio_id", "PORT_002"),
        ("product", "HoldingsAsOf"),
        ("as_of_date", date(2026, 2, 26)),
        ("position_epoch", 8),
        ("cashflow_epoch", 6),
        ("valuation_date", date(2026, 2, 26)),
        ("transaction_window_end", date(2026, 2, 26)),
        ("policy_version", "tenant-default-v2"),
    ],
)
def test_portfolio_snapshot_id_changes_when_source_scope_changes(field_name, value) -> None:
    baseline = build_portfolio_snapshot_id(_scope())
    changed = build_portfolio_snapshot_id(_scope(**{field_name: value}))

    assert changed != baseline


def test_portfolio_snapshot_id_rejects_invalid_scope() -> None:
    with pytest.raises(ValueError, match="transaction_window_start"):
        build_portfolio_snapshot_id(
            _scope(
                transaction_window_start=date(2026, 3, 1),
                transaction_window_end=date(2026, 2, 27),
            )
        )

    with pytest.raises(ValueError, match="portfolio_id is required"):
        build_portfolio_snapshot_id(_scope(portfolio_id=" "))

    with pytest.raises(ValueError, match="position_epoch must be non-negative"):
        build_portfolio_snapshot_id(_scope(position_epoch=-1))

    with pytest.raises(ValueError, match="must be provided together"):
        build_portfolio_snapshot_id(_scope(transaction_window_end=None))

    with pytest.raises(ValueError, match="source_data_products is required"):
        build_portfolio_snapshot_id(_scope(source_data_products=("HoldingsAsOf", " ")))
