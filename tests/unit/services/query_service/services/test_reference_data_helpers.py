from datetime import UTC, date, datetime
from decimal import Decimal
from types import SimpleNamespace

from portfolio_common.reconciliation_quality import BLOCKED, PARTIAL

from src.services.query_service.app.services.reference_data_helpers import (
    latest_effective_records,
    latest_reference_evidence_timestamp,
    market_reference_data_quality_status,
    resolve_component_window_rows,
)


def test_latest_reference_evidence_timestamp_uses_durable_reference_timestamps() -> None:
    older_source_timestamp = datetime(2026, 1, 2, 9, 0, tzinfo=UTC)
    latest_updated_at = datetime(2026, 1, 3, 11, 0, tzinfo=UTC)

    assert (
        latest_reference_evidence_timestamp(
            [
                SimpleNamespace(source_timestamp=older_source_timestamp),
                SimpleNamespace(updated_at=latest_updated_at),
            ]
        )
        == latest_updated_at
    )


def test_market_reference_data_quality_classifies_reference_rows() -> None:
    assert (
        market_reference_data_quality_status(
            [
                SimpleNamespace(quality_status="accepted"),
                SimpleNamespace(quality_status="estimated"),
                SimpleNamespace(quality_status="accepted"),
            ],
            required_count=3,
        )
        == PARTIAL
    )
    assert (
        market_reference_data_quality_status(
            [SimpleNamespace(quality_status="blocked")],
            required_count=1,
        )
        == BLOCKED
    )
    assert market_reference_data_quality_status([SimpleNamespace()], required_count=1) == "UNKNOWN"


def test_latest_effective_records_keeps_latest_row_per_business_key() -> None:
    rows = [
        SimpleNamespace(index_id="IDX_B", component_id="SEC_2", effective_from=date(2026, 1, 1)),
        SimpleNamespace(index_id="IDX_A", component_id="SEC_1", effective_from=date(2026, 1, 1)),
        SimpleNamespace(index_id="IDX_A", component_id="SEC_1", effective_from=date(2026, 2, 1)),
    ]

    latest_rows = latest_effective_records(
        rows,
        key_fields=("index_id", "component_id"),
        effective_from_field="effective_from",
    )

    assert [(row.index_id, row.component_id, row.effective_from) for row in latest_rows] == [
        ("IDX_A", "SEC_1", date(2026, 2, 1)),
        ("IDX_B", "SEC_2", date(2026, 1, 1)),
    ]


def test_resolve_component_window_rows_infers_superseded_effective_end_dates() -> None:
    rows = [
        SimpleNamespace(
            index_id="IDX_A",
            composition_weight=Decimal("0.60"),
            composition_effective_from=date(2026, 1, 1),
            composition_effective_to=None,
            quality_status="accepted",
            observed_at=datetime(2026, 1, 1, 8, tzinfo=UTC),
        ),
        SimpleNamespace(
            index_id="IDX_A",
            composition_weight=Decimal("0.55"),
            composition_effective_from=date(2026, 2, 1),
            composition_effective_to=None,
            quality_status="accepted",
            observed_at=datetime(2026, 2, 1, 8, tzinfo=UTC),
        ),
    ]

    resolved_rows = resolve_component_window_rows(
        rows,
        start_date=date(2026, 1, 15),
        end_date=date(2026, 2, 15),
    )

    resolved_windows = [
        (row.composition_effective_from, row.composition_effective_to) for row in resolved_rows
    ]

    assert resolved_windows == [
        (date(2026, 1, 1), date(2026, 1, 31)),
        (date(2026, 2, 1), None),
    ]


def test_resolve_component_window_rows_preserves_earlier_explicit_end_date() -> None:
    rows = [
        SimpleNamespace(
            index_id="IDX_A",
            composition_weight=Decimal("0.60"),
            composition_effective_from=date(2026, 1, 1),
            composition_effective_to=date(2026, 1, 20),
            rebalance_event_id="REB_001",
            quality_status="accepted",
            source_timestamp=datetime(2026, 1, 1, 8, tzinfo=UTC),
            updated_at=datetime(2026, 1, 1, 9, tzinfo=UTC),
        ),
        SimpleNamespace(
            index_id="IDX_A",
            composition_weight=Decimal("0.55"),
            composition_effective_from=date(2026, 2, 1),
            composition_effective_to=None,
            quality_status="accepted",
        ),
    ]

    resolved_rows = resolve_component_window_rows(
        rows,
        start_date=date(2026, 1, 15),
        end_date=date(2026, 2, 15),
    )

    assert [
        (row.composition_effective_from, row.composition_effective_to) for row in resolved_rows
    ] == [
        (date(2026, 1, 1), date(2026, 1, 20)),
        (date(2026, 2, 1), None),
    ]
    assert resolved_rows[0].rebalance_event_id == "REB_001"
    assert resolved_rows[0].source_timestamp == datetime(2026, 1, 1, 8, tzinfo=UTC)
    assert resolved_rows[0].updated_at == datetime(2026, 1, 1, 9, tzinfo=UTC)


def test_resolve_component_window_rows_filters_non_overlapping_windows() -> None:
    rows = [
        SimpleNamespace(
            index_id="IDX_A",
            composition_weight=Decimal("0.60"),
            composition_effective_from=date(2026, 1, 1),
            composition_effective_to=date(2026, 1, 15),
        ),
        SimpleNamespace(
            index_id="IDX_A",
            composition_weight=Decimal("0.55"),
            composition_effective_from=date(2026, 2, 1),
            composition_effective_to=date(2026, 2, 28),
        ),
        SimpleNamespace(
            index_id="IDX_B",
            composition_weight=Decimal("1.00"),
            composition_effective_from=date(2026, 4, 1),
            composition_effective_to=None,
        ),
    ]

    resolved_rows = resolve_component_window_rows(
        rows,
        start_date=date(2026, 2, 1),
        end_date=date(2026, 3, 31),
    )

    assert [(row.index_id, row.composition_effective_from) for row in resolved_rows] == [
        ("IDX_A", date(2026, 2, 1)),
    ]
