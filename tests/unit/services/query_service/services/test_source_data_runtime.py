from datetime import UTC, date, datetime

from src.services.query_service.app.services.source_data_runtime import (
    source_product_runtime_metadata,
    source_product_runtime_metadata_without_as_of_date,
)


def test_source_product_runtime_metadata_defaults_unknown_quality() -> None:
    metadata = source_product_runtime_metadata(date(2026, 5, 31))

    assert metadata["as_of_date"] == date(2026, 5, 31)
    assert metadata["data_quality_status"] == "UNKNOWN"
    assert metadata["reconciliation_status"] == "UNKNOWN"
    assert metadata["restatement_version"] == "current"
    assert metadata["generated_at"].tzinfo is not None
    assert metadata["content_hash"].startswith("sha256:")
    assert metadata["source_digest"] == metadata["content_hash"]
    assert metadata["source_evidence_current"] is False


def test_source_product_runtime_metadata_preserves_quality_and_evidence_timestamp() -> None:
    evidence_timestamp = datetime(2026, 5, 31, 8, 45, tzinfo=UTC)

    metadata = source_product_runtime_metadata(
        date(2026, 5, 31),
        tenant_id=" tenant-sg ",
        data_quality_status="COMPLETE",
        latest_evidence_timestamp=evidence_timestamp,
    )

    assert metadata["tenant_id"] == "tenant-sg"
    assert metadata["data_quality_status"] == "COMPLETE"
    assert metadata["latest_evidence_timestamp"] == evidence_timestamp
    assert metadata["source_evidence_current"] is True


def test_source_product_runtime_metadata_without_as_of_date_removes_duplicate_field() -> None:
    metadata = source_product_runtime_metadata_without_as_of_date(
        date(2026, 5, 31),
        tenant_id="tenant-sg",
        data_quality_status="PARTIAL",
    )

    assert "as_of_date" not in metadata
    assert metadata["tenant_id"] == "tenant-sg"
    assert metadata["data_quality_status"] == "PARTIAL"
    assert metadata["content_hash"].startswith("sha256:")
