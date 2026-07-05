from datetime import UTC, datetime

from portfolio_common.reconciliation_quality import COMPLETE, PARTIAL, UNKNOWN

from src.services.query_service.app.dtos.core_snapshot_dto import (
    CoreSnapshotFreshnessMetadata,
)
from src.services.query_service.app.services.core_snapshot_quality import (
    snapshot_data_quality_status,
)


def test_snapshot_data_quality_status_classifies_snapshot_evidence() -> None:
    assert (
        snapshot_data_quality_status(
            freshness=CoreSnapshotFreshnessMetadata(
                freshness_status=" current_snapshot ",
                baseline_source="position_state",
                snapshot_timestamp=datetime(2026, 2, 27, 10, 5, tzinfo=UTC),
                snapshot_epoch=7,
            ),
            baseline_count=1,
        )
        == COMPLETE
    )
    assert (
        snapshot_data_quality_status(
            freshness=CoreSnapshotFreshnessMetadata(
                freshness_status="CURRENT_SNAPSHOT",
                baseline_source="position_state",
                snapshot_timestamp=datetime(2026, 2, 27, 10, 5, tzinfo=UTC),
                snapshot_epoch=None,
            ),
            baseline_count=2,
        )
        == PARTIAL
    )
    assert (
        snapshot_data_quality_status(
            freshness=CoreSnapshotFreshnessMetadata(
                freshness_status=" historical_fallback ",
                baseline_source="position_history",
                fallback_reason="NO_CURRENT_POSITION_STATE_ROWS",
            ),
            baseline_count=1,
        )
        == PARTIAL
    )
    assert (
        snapshot_data_quality_status(
            freshness=CoreSnapshotFreshnessMetadata(
                freshness_status="HISTORICAL_FALLBACK",
                baseline_source="position_history",
                fallback_reason="NO_CURRENT_POSITION_STATE_ROWS",
            ),
            baseline_count=0,
        )
        == UNKNOWN
    )
