from datetime import date

from portfolio_common.effective_dated_replay import (
    merge_replay_sibling_evidence,
    validated_effective_dated_replay_identity,
)
from portfolio_common.reprocessing_payload_integrity import (
    PendingReplaySiblingEvidence,
    RetainedReplaySibling,
)


def _identity(job_type: str, payload: dict, *, attempt_count: int, correlation_id: str | None):
    return validated_effective_dated_replay_identity(
        job_type=job_type,
        payload=payload,
        attempt_count=attempt_count,
        correlation_id=correlation_id,
        correlation_missing_reason=None,
        alternate_lookup_key=None,
    )


def _sibling(
    payload: dict,
    *,
    attempt_count: int,
    correlation_id: str | None,
) -> RetainedReplaySibling:
    return RetainedReplaySibling(
        id=12,
        payload=payload,
        earliest_impacted_date=date.fromisoformat(payload["earliest_impacted_date"]),
        attempt_count=attempt_count,
        correlation_id=correlation_id,
        correlation_missing_reason=None,
        alternate_lookup_key=None,
    )


def test_fx_sibling_merge_preserves_boundary_retry_history_and_latest_source() -> None:
    owned = _identity(
        "RESET_FX_WATERMARKS",
        {
            "from_currency": "USD",
            "to_currency": "CHF",
            "earliest_impacted_date": "2025-01-07",
            "generated_at": "2025-01-07T00:00:00+00:00",
            "content_hash": "sha256:owned",
        },
        attempt_count=1,
        correlation_id="corr-owned",
    )
    sibling = _sibling(
        {
            "from_currency": "USD",
            "to_currency": "CHF",
            "earliest_impacted_date": "2025-01-03",
            "generated_at": "2025-01-08T00:00:00+00:00",
            "content_hash": "sha256:sibling",
        },
        attempt_count=5,
        correlation_id="corr-sibling",
    )

    merged = merge_replay_sibling_evidence(
        owned,
        PendingReplaySiblingEvidence((sibling,)),
    )

    assert merged.payload["earliest_impacted_date"] == "2025-01-03"
    assert merged.payload["content_hash"] == "sha256:sibling"
    assert merged.generated_at.isoformat() == "2025-01-08T00:00:00+00:00"
    assert merged.attempt_count == 5
    assert merged.correlation_id == "corr-sibling"


def test_invalid_fx_sibling_contributes_boundary_and_attempts_but_not_source() -> None:
    owned = _identity(
        "RESET_FX_WATERMARKS",
        {
            "from_currency": "USD",
            "to_currency": "CHF",
            "earliest_impacted_date": "2025-01-07",
            "generated_at": "2025-01-07T00:00:00+00:00",
            "content_hash": "sha256:owned",
        },
        attempt_count=1,
        correlation_id="corr-owned",
    )
    sibling = _sibling(
        {
            "from_currency": " USD ",
            "to_currency": "CHF",
            "earliest_impacted_date": "2025-01-03",
            "generated_at": "invalid",
            "content_hash": "legacy",
        },
        attempt_count=4,
        correlation_id="corr-invalid",
    )

    merged = merge_replay_sibling_evidence(
        owned,
        PendingReplaySiblingEvidence((sibling,)),
    )

    assert merged.payload["earliest_impacted_date"] == "2025-01-03"
    assert merged.payload["content_hash"] == "sha256:owned"
    assert merged.attempt_count == 4
    assert merged.correlation_id == "corr-owned"


def test_reset_sibling_merge_attributes_an_earlier_boundary_to_its_lineage() -> None:
    owned = _identity(
        "RESET_WATERMARKS",
        {"security_id": "BOND-1", "earliest_impacted_date": "2025-01-07"},
        attempt_count=1,
        correlation_id="corr-owned",
    )
    sibling = _sibling(
        {"security_id": "BOND-1", "earliest_impacted_date": "2025-01-03"},
        attempt_count=3,
        correlation_id="corr-sibling",
    )

    merged = merge_replay_sibling_evidence(
        owned,
        PendingReplaySiblingEvidence((sibling,)),
    )

    assert merged.payload["earliest_impacted_date"] == "2025-01-03"
    assert merged.attempt_count == 3
    assert merged.correlation_id == "corr-sibling"


def test_reset_sibling_merge_fills_missing_lineage_at_equal_boundary() -> None:
    owned = _identity(
        "RESET_WATERMARKS",
        {"security_id": "BOND-1", "earliest_impacted_date": "2025-01-03"},
        attempt_count=2,
        correlation_id=None,
    )
    sibling = _sibling(
        {"security_id": "BOND-1", "earliest_impacted_date": "2025-01-03"},
        attempt_count=3,
        correlation_id="corr-sibling",
    )

    merged = merge_replay_sibling_evidence(
        owned,
        PendingReplaySiblingEvidence((sibling,)),
    )

    assert merged.payload["earliest_impacted_date"] == "2025-01-03"
    assert merged.attempt_count == 3
    assert merged.correlation_id == "corr-sibling"
    assert merged.correlation_missing_reason is None
    assert merged.alternate_lookup_key is None


def test_reset_sibling_merge_keeps_owned_lineage_when_earlier_sibling_lacks_it() -> None:
    owned = _identity(
        "RESET_WATERMARKS",
        {"security_id": "BOND-1", "earliest_impacted_date": "2025-01-07"},
        attempt_count=2,
        correlation_id="corr-owned",
    )
    sibling = _sibling(
        {"security_id": "BOND-1", "earliest_impacted_date": "2025-01-03"},
        attempt_count=3,
        correlation_id=None,
    )

    merged = merge_replay_sibling_evidence(
        owned,
        PendingReplaySiblingEvidence((sibling,)),
    )

    assert merged.payload["earliest_impacted_date"] == "2025-01-03"
    assert merged.attempt_count == 3
    assert merged.correlation_id == "corr-owned"
    assert merged.correlation_missing_reason is None
    assert merged.alternate_lookup_key is None


def test_reset_sibling_merge_uses_existing_sibling_lineage_at_equal_boundary() -> None:
    owned = _identity(
        "RESET_WATERMARKS",
        {"security_id": "BOND-1", "earliest_impacted_date": "2025-01-03"},
        attempt_count=2,
        correlation_id="corr-owned",
    )
    sibling = _sibling(
        {"security_id": "BOND-1", "earliest_impacted_date": "2025-01-03"},
        attempt_count=3,
        correlation_id="corr-existing-sibling",
    )

    merged = merge_replay_sibling_evidence(
        owned,
        PendingReplaySiblingEvidence((sibling,)),
    )

    assert merged.correlation_id == "corr-existing-sibling"
