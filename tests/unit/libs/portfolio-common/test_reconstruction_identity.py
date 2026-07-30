from datetime import UTC, date, datetime, timedelta, timezone
from decimal import Decimal

import pytest
from portfolio_common.reconstruction_identity import (
    PortfolioReconstructionScope,
    ProductReconstructionScope,
    build_portfolio_snapshot_id,
    build_reconstruction_scope_evidence,
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
    assert first == "pss_2cb6ac4ce2e9efe97eacb8a81ec8053d"


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


def _product_scope(**overrides) -> ProductReconstructionScope:
    values = {
        "product": "TransactionLedgerWindow",
        "portfolio_id": "PORT_001",
        "as_of_date": date(2026, 2, 27),
        "source_data_products": ("TransactionLedgerWindow", "InstrumentMaster"),
        "restatement_version": "current",
        "policy_version": "transaction-ledger-window-v1",
        "qualifiers": (
            ("start_date", date(2026, 1, 1)),
            ("security_id", "SEC_001"),
            ("include_projected", False),
        ),
        "material_evidence": (
            ("total_count", 17),
            ("latest_evidence_timestamp", datetime(2026, 2, 27, 10, 5, tzinfo=UTC)),
        ),
    }
    values.update(overrides)
    return ProductReconstructionScope(**values)


def test_reconstruction_scope_evidence_normalizes_entry_and_source_product_order() -> None:
    first = build_reconstruction_scope_evidence(_product_scope())
    second = build_reconstruction_scope_evidence(
        _product_scope(
            source_data_products=(
                "InstrumentMaster",
                "TransactionLedgerWindow",
                "InstrumentMaster",
            ),
            qualifiers=(
                ("include_projected", False),
                ("security_id", "SEC_001"),
                ("start_date", date(2026, 1, 1)),
            ),
            material_evidence=(
                ("latest_evidence_timestamp", datetime(2026, 2, 27, 10, 5, tzinfo=UTC)),
                ("total_count", 17),
            ),
        )
    )

    assert first == second
    assert first.scope_id.startswith("rs_")
    assert first.scope_content_hash.startswith("sha256:")
    assert first.source_data_products == ("InstrumentMaster", "TransactionLedgerWindow")
    assert first.lineage()["reconstruction_scope_id"] == first.scope_id
    assert first.lineage()["reconstruction_restatement_version"] == "current"


def test_reconstruction_scope_evidence_normalizes_equivalent_instants_to_utc() -> None:
    utc_evidence = build_reconstruction_scope_evidence(
        _product_scope(
            material_evidence=(
                ("latest_evidence_timestamp", datetime(2026, 2, 27, 10, 5, tzinfo=UTC)),
            )
        )
    )
    offset_evidence = build_reconstruction_scope_evidence(
        _product_scope(
            material_evidence=(
                (
                    "latest_evidence_timestamp",
                    datetime(
                        2026,
                        2,
                        27,
                        18,
                        5,
                        tzinfo=timezone(timedelta(hours=8)),
                    ),
                ),
            )
        )
    )

    assert utc_evidence == offset_evidence


@pytest.mark.parametrize(
    "overrides",
    [
        {"restatement_version": "restatement_0002"},
        {"policy_version": "transaction-ledger-window-v2"},
        {"qualifiers": (("security_id", "SEC_002"),)},
        {"qualifiers": (("security_id", 1),)},
        {"material_evidence": (("total_count", 18),)},
    ],
)
def test_reconstruction_scope_evidence_changes_with_material_scope(overrides) -> None:
    baseline = build_reconstruction_scope_evidence(_product_scope())

    changed = build_reconstruction_scope_evidence(_product_scope(**overrides))

    assert changed.scope_id != baseline.scope_id
    assert changed.scope_content_hash != baseline.scope_content_hash


def test_reconstruction_scope_evidence_rejects_ambiguous_entries() -> None:
    with pytest.raises(ValueError, match="qualifiers contains duplicate key: security_id"):
        build_reconstruction_scope_evidence(
            _product_scope(
                qualifiers=(
                    ("security_id", "SEC_001"),
                    ("security_id", "SEC_002"),
                )
            )
        )

    with pytest.raises(ValueError, match="source_data_products is required"):
        build_reconstruction_scope_evidence(_product_scope(source_data_products=()))

    with pytest.raises(TypeError, match="qualifiers.unsupported"):
        build_reconstruction_scope_evidence(
            _product_scope(qualifiers=(("unsupported", Decimal("1.0")),))
        )

    with pytest.raises(
        ValueError,
        match="material_evidence.latest_evidence_timestamp datetime must be timezone-aware",
    ):
        build_reconstruction_scope_evidence(
            _product_scope(
                material_evidence=(("latest_evidence_timestamp", datetime(2026, 2, 27, 10, 5)),)
            )
        )
