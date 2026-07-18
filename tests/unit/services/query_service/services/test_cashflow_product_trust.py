from datetime import UTC, datetime
from decimal import Decimal

from src.services.query_service.app.services.cashflow_product_trust import (
    EMPTY_SOURCE_WINDOW,
    SOURCE_COUNT_MISMATCH,
    SOURCE_EVIDENCE_TIMESTAMP_MISSING,
    SOURCE_TOTAL_MISMATCH,
    reconcile_cashflow_window,
)


def test_cashflow_window_is_supported_when_counts_and_totals_reconcile() -> None:
    trust = reconcile_cashflow_window(
        source_row_count=3,
        calculated_source_row_count=3,
        output_group_count=2,
        source_component_totals={"USD": Decimal("8")},
        calculated_component_totals={"USD": Decimal("8.0")},
        latest_evidence_timestamp=datetime(2026, 3, 5, tzinfo=UTC),
    )

    assert trust.reconciliation_status == "COMPLETE"
    assert trust.response.window_status == "POPULATED"
    assert trust.response.supportability_status == "SUPPORTED"
    assert trust.response.reason_codes == []
    assert trust.source_evidence_current is True


def test_cashflow_window_explicitly_supports_empty_source_without_timestamp() -> None:
    trust = reconcile_cashflow_window(
        source_row_count=0,
        calculated_source_row_count=0,
        output_group_count=31,
        source_component_totals={"BOOKED": Decimal("0")},
        calculated_component_totals={"BOOKED": Decimal("0")},
        latest_evidence_timestamp=None,
    )

    assert trust.reconciliation_status == "COMPLETE"
    assert trust.response.window_status == "EMPTY"
    assert trust.response.reason_codes == [EMPTY_SOURCE_WINDOW]
    assert trust.source_evidence_current is True
    assert trust.freshness_status == "CURRENT"


def test_cashflow_window_fails_closed_on_source_control_mismatches() -> None:
    trust = reconcile_cashflow_window(
        source_row_count=3,
        calculated_source_row_count=2,
        output_group_count=2,
        source_component_totals={"USD": Decimal("8")},
        calculated_component_totals={"USD": Decimal("7")},
        latest_evidence_timestamp=None,
    )

    assert trust.reconciliation_status == "BLOCKED"
    assert trust.data_quality_status == "BLOCKED"
    assert trust.response.window_status == "DEGRADED"
    assert trust.response.supportability_status == "UNAVAILABLE"
    assert trust.response.reason_codes == [
        SOURCE_COUNT_MISMATCH,
        SOURCE_TOTAL_MISMATCH,
        SOURCE_EVIDENCE_TIMESTAMP_MISSING,
    ]
    assert trust.source_evidence_current is False


def test_cashflow_window_rejects_nonzero_total_for_zero_source_rows() -> None:
    trust = reconcile_cashflow_window(
        source_row_count=0,
        calculated_source_row_count=0,
        output_group_count=1,
        source_component_totals={"USD": Decimal("1")},
        calculated_component_totals={"USD": Decimal("1")},
        latest_evidence_timestamp=None,
    )

    assert trust.reconciliation_status == "BLOCKED"
    assert trust.response.reason_codes == [SOURCE_TOTAL_MISMATCH]
