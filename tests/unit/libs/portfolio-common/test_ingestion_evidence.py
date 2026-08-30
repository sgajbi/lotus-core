from datetime import UTC, datetime, timedelta, timezone

import pytest
from portfolio_common.ingestion_evidence import (
    ACCEPTED,
    EMPTY,
    PARTIALLY_ACCEPTED,
    QUARANTINED,
    REJECTED,
    IngestionEvidenceBundleIdentityScope,
    IngestionOutcomeCounts,
    SourceBatchIdentityScope,
    build_ingestion_evidence_bundle_id,
    build_source_batch_fingerprint,
    classify_ingestion_outcome,
    derive_source_batch_evidence,
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


def test_source_batch_fingerprint_normalizes_text_and_observed_at_timezone() -> None:
    first = build_source_batch_fingerprint(_scope())
    second = build_source_batch_fingerprint(
        _scope(
            source_system=" custodian_sftp ",
            source_batch_id=" batch_20260415_001 ",
            payload_kind=" transactions ",
            tenant_id=" tenant_sg_pb ",
            feed_name=" daily_transactions ",
            observed_at=datetime(2026, 4, 15, 9, 30, tzinfo=timezone(timedelta(hours=8))),
            source_record_keys=(" TXN_1 ", " TXN_2 "),
        )
    )

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

    with pytest.raises(ValueError, match="datetime values must be timezone-aware"):
        build_source_batch_fingerprint(_scope(observed_at=datetime(2026, 4, 15, 1, 30)))


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


def test_source_batch_evidence_is_derived_only_from_unambiguous_source_payload() -> None:
    evidence = derive_source_batch_evidence(
        {
            "tenant_id": "tenant-sg",
            "transactions": [
                {
                    "transaction_id": "TXN-002",
                    "source_system": "custody-feed",
                    "source_batch_id": "batch-001",
                },
                {
                    "transaction_id": "TXN-001",
                    "source_system": "custody-feed",
                    "source_batch_id": "batch-001",
                },
            ],
        },
        payload_kind="transaction",
    )

    assert evidence is not None
    assert evidence.source_system == "custody-feed"
    assert evidence.source_batch_id == "batch-001"
    assert evidence.source_record_keys == ("TXN-001", "TXN-002")
    assert evidence.source_batch_fingerprint.startswith("srcbatch_")


@pytest.mark.parametrize(
    "payload",
    [
        {"transactions": [{"transaction_id": "TXN-001"}]},
        {
            "transactions": [
                {
                    "source_system": "custody-feed",
                    "source_batch_id": "batch-001",
                },
                {
                    "source_system": "custody-feed",
                    "source_batch_id": "batch-002",
                },
            ]
        },
        {
            "transactions": [
                {
                    "source_system": "custody-feed",
                    "source_batch_id": "batch-001",
                },
                {
                    "source_system": "transfer-agent",
                    "source_batch_id": "batch-001",
                },
            ]
        },
        {
            "transactions": [
                {
                    "source_system": "custody-feed",
                    "source_batch_id": "batch-001",
                },
                {
                    "source_system": "custody-feed",
                },
            ]
        },
    ],
)
def test_source_batch_evidence_remains_absent_without_single_source_authority(payload) -> None:
    assert (
        derive_source_batch_evidence(
            {"tenant_id": "tenant-sg", **payload},
            payload_kind="transaction",
        )
        is None
    )


@pytest.mark.parametrize(
    "payload",
    [
        {
            "transactions": [
                {
                    "source_system": "custody-feed",
                    "source_batch_id": "batch-001",
                }
            ]
        },
        {
            "tenant_id": " ",
            "transactions": [
                {
                    "source_system": "custody-feed",
                    "source_batch_id": "batch-001",
                }
            ],
        },
        {
            "transactions": [
                {
                    "tenant_id": "tenant-sg",
                    "source_system": "custody-feed",
                    "source_batch_id": "batch-001",
                },
                {
                    "tenant_id": "tenant-hk",
                    "source_system": "custody-feed",
                    "source_batch_id": "batch-001",
                },
            ]
        },
    ],
)
def test_source_batch_evidence_requires_one_source_owned_tenant(payload) -> None:
    assert derive_source_batch_evidence(payload, payload_kind="transaction") is None


def test_evidence_bundle_identity_is_order_insensitive_and_state_sensitive() -> None:
    first = build_ingestion_evidence_bundle_id(
        IngestionEvidenceBundleIdentityScope(
            job_id="job-001",
            endpoint="/ingest/transactions",
            entity_type="transaction",
            accepted_count=2,
            job_state="queued|1",
            request_payload_fingerprint="sha256:payload",
            failure_ids=("failure-002", "failure-001"),
            replay_ids=("replay-001",),
            consumer_dlq_event_ids=("dlq-002", "dlq-001"),
        )
    )
    reordered = build_ingestion_evidence_bundle_id(
        IngestionEvidenceBundleIdentityScope(
            job_id="job-001",
            endpoint="/ingest/transactions",
            entity_type="transaction",
            accepted_count=2,
            job_state="queued|1",
            request_payload_fingerprint="sha256:payload",
            failure_ids=("failure-001", "failure-002", "failure-001"),
            replay_ids=("replay-001",),
            consumer_dlq_event_ids=("dlq-001", "dlq-002"),
        )
    )
    changed_state = build_ingestion_evidence_bundle_id(
        IngestionEvidenceBundleIdentityScope(
            job_id="job-001",
            endpoint="/ingest/transactions",
            entity_type="transaction",
            accepted_count=2,
            job_state="queued|2",
            request_payload_fingerprint="sha256:payload",
            failure_ids=("failure-001", "failure-002"),
            replay_ids=("replay-001",),
            consumer_dlq_event_ids=("dlq-001", "dlq-002"),
        )
    )

    assert first == reordered
    assert first.startswith("ingev_")
    assert changed_state != first
