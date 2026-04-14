from datetime import UTC, datetime

import pytest
from portfolio_common.ingestion_evidence import (
    ACCEPTED,
    EMPTY,
    PARTIALLY_ACCEPTED,
    QUARANTINED,
    REJECTED,
    IngestionOutcomeCounts,
    SourceBatchIdentityScope,
    build_source_batch_fingerprint,
    classify_ingestion_outcome,
)


def _scope(**overrides) -> SourceBatchIdentityScope:
    values = {
        "source_system": "custodian_sftp",
        "source_batch_id": "batch_20260415_001",
        "payload_kind": "transactions",
        "tenant_id": "tenant_sg_pb",
        "feed_name": "daily_transactions",
        "observed_at": datetime(2026, 4, 15, 1, 30, tzinfo=UTC),
        "ingested_at": datetime(2026, 4, 15, 1, 45, tzinfo=UTC),
        "idempotency_key": "ingest-transactions-20260415",
        "correlation_id": "corr_001",
        "source_record_keys": ("TXN_2", "TXN_1"),
    }
    values.update(overrides)
    return SourceBatchIdentityScope(**values)


def test_source_batch_fingerprint_is_deterministic_for_same_scope() -> None:
    first = build_source_batch_fingerprint(_scope())
    second = build_source_batch_fingerprint(_scope())

    assert first == second
    assert first.startswith("srcbatch_")
    assert len(first) == len("srcbatch_") + 32


def test_source_batch_fingerprint_ignores_record_key_order_and_duplicates() -> None:
    first = build_source_batch_fingerprint(_scope(source_record_keys=("TXN_2", "TXN_1", "TXN_1")))
    second = build_source_batch_fingerprint(_scope(source_record_keys=("TXN_1", "TXN_2")))

    assert first == second


def test_source_batch_fingerprint_ignores_ingestion_attempt_metadata() -> None:
    first = build_source_batch_fingerprint(_scope())
    second = build_source_batch_fingerprint(
        _scope(
            ingested_at=datetime(2026, 4, 15, 3, 45, tzinfo=UTC),
            idempotency_key="retry-key",
            correlation_id="retry-correlation",
        )
    )

    assert first == second


@pytest.mark.parametrize(
    ("field_name", "value"),
    [
        ("source_system", "custodian_api"),
        ("source_batch_id", "batch_20260415_002"),
        ("payload_kind", "market_prices"),
        ("tenant_id", "tenant_hk_pb"),
        ("feed_name", "intraday_transactions"),
        ("observed_at", datetime(2026, 4, 15, 2, 30, tzinfo=UTC)),
    ],
)
def test_source_batch_fingerprint_changes_when_scope_changes(field_name, value) -> None:
    baseline = build_source_batch_fingerprint(_scope())
    changed = build_source_batch_fingerprint(_scope(**{field_name: value}))

    assert changed != baseline


def test_source_batch_fingerprint_rejects_invalid_scope() -> None:
    with pytest.raises(ValueError, match="source_system is required"):
        build_source_batch_fingerprint(_scope(source_system=" "))

    with pytest.raises(ValueError, match="source_record_keys is required"):
        build_source_batch_fingerprint(_scope(source_record_keys=("TXN_1", " ")))


@pytest.mark.parametrize(
    ("counts", "expected"),
    [
        (IngestionOutcomeCounts(accepted_count=10), ACCEPTED),
        (IngestionOutcomeCounts(accepted_count=8, rejected_count=2), PARTIALLY_ACCEPTED),
        (IngestionOutcomeCounts(accepted_count=8, quarantined_count=2), PARTIALLY_ACCEPTED),
        (IngestionOutcomeCounts(rejected_count=2), REJECTED),
        (IngestionOutcomeCounts(quarantined_count=2), QUARANTINED),
        (IngestionOutcomeCounts(), EMPTY),
    ],
)
def test_classify_ingestion_outcome(counts, expected) -> None:
    assert classify_ingestion_outcome(counts) == expected


def test_classify_ingestion_outcome_rejects_negative_counts() -> None:
    with pytest.raises(ValueError, match="accepted_count must be non-negative"):
        classify_ingestion_outcome(IngestionOutcomeCounts(accepted_count=-1))
