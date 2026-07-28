from types import SimpleNamespace

import pytest

from src.services.ingestion_service.app.application.ingestion_idempotency_replay import (
    IngestionIdempotencyReplayDisposition,
    resolve_ingestion_idempotency_replay,
)


def _job(
    *,
    status: str,
    failure_reason: str | None = None,
    failure_status_code: int | None = None,
    failure_code: str | None = None,
    failure_detail: dict | None = None,
    failure_headers: dict[str, str] | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        job_id="ing_job_001",
        status=status,
        failure_reason=failure_reason,
        failure_status_code=failure_status_code,
        failure_code=failure_code,
        failure_detail=failure_detail,
        failure_headers=failure_headers,
    )


def test_queued_job_is_replay_safe() -> None:
    resolution = resolve_ingestion_idempotency_replay(_job(status="queued"))

    assert resolution.accepted is True
    assert resolution.disposition is IngestionIdempotencyReplayDisposition.ACCEPTED
    assert resolution.status_code is None
    assert resolution.detail is None


def test_failed_job_replays_durable_failure_outcome_without_mutating_evidence() -> None:
    stored_detail = {
        "message": "Competing source version.",
        "source_scope": "LOTUS_PB_SG|SG_PRIVATE_BANK_BOOK",
    }
    resolution = resolve_ingestion_idempotency_replay(
        _job(
            status="failed",
            failure_reason="Competing source version.",
            failure_status_code=409,
            failure_code="MARKET_PRICE_SOURCE_FACT_CONFLICT",
            failure_detail=stored_detail,
            failure_headers={"Retry-After": "30"},
        )
    )

    assert resolution.accepted is False
    assert resolution.disposition is IngestionIdempotencyReplayDisposition.FAILED
    assert resolution.status_code == 409
    assert resolution.detail == {
        "code": "MARKET_PRICE_SOURCE_FACT_CONFLICT",
        "message": "Competing source version.",
        "source_scope": "LOTUS_PB_SG|SG_PRIVATE_BANK_BOOK",
        "job_id": "ing_job_001",
    }
    assert resolution.headers == {"Retry-After": "30"}
    assert stored_detail == {
        "message": "Competing source version.",
        "source_scope": "LOTUS_PB_SG|SG_PRIVATE_BANK_BOOK",
    }


def test_durable_failure_outcome_takes_precedence_over_nonterminal_status() -> None:
    resolution = resolve_ingestion_idempotency_replay(
        _job(
            status="accepted",
            failure_reason="Queue transition failed after persistence.",
            failure_status_code=500,
            failure_code="INGESTION_JOB_BOOKKEEPING_FAILED",
            failure_detail={"work_state": "persisted", "retry_safe": False},
        )
    )

    assert resolution.disposition is IngestionIdempotencyReplayDisposition.FAILED
    assert resolution.status_code == 500
    assert resolution.detail == {
        "code": "INGESTION_JOB_BOOKKEEPING_FAILED",
        "message": "The previous ingestion attempt failed.",
        "work_state": "persisted",
        "retry_safe": False,
        "job_id": "ing_job_001",
    }


def test_legacy_failed_job_fails_closed_without_exposing_recorded_reason() -> None:
    resolution = resolve_ingestion_idempotency_replay(
        _job(
            status="failed",
            failure_reason=(
                "password authentication failed for user internal_writer at postgres.service.local"
            ),
        )
    )

    assert resolution.disposition is IngestionIdempotencyReplayDisposition.FAILED
    assert resolution.status_code == 500
    assert resolution.detail == {
        "code": "INGESTION_PREVIOUS_ATTEMPT_FAILED",
        "message": "The previous ingestion attempt failed.",
        "job_id": "ing_job_001",
    }


def test_durable_failure_without_client_detail_does_not_expose_recorded_reason() -> None:
    resolution = resolve_ingestion_idempotency_replay(
        _job(
            status="failed",
            failure_reason="broker sasl authentication failed at kafka.internal:9093",
            failure_status_code=503,
            failure_code="INGESTION_PUBLISH_FAILED",
        )
    )

    assert resolution.status_code == 503
    assert resolution.detail == {
        "code": "INGESTION_PUBLISH_FAILED",
        "message": "The previous ingestion attempt failed.",
        "job_id": "ing_job_001",
    }


def test_accepted_job_reports_truthful_nonterminal_outcome() -> None:
    resolution = resolve_ingestion_idempotency_replay(_job(status="accepted"))

    assert resolution.disposition is IngestionIdempotencyReplayDisposition.IN_PROGRESS
    assert resolution.status_code == 409
    assert resolution.detail == {
        "code": "INGESTION_REQUEST_IN_PROGRESS",
        "message": "The original ingestion request has not reached a replay-safe state.",
        "job_id": "ing_job_001",
        "status": "accepted",
    }


@pytest.mark.parametrize("status", ["", "completed", "persisted", "FAILED"])
def test_unknown_job_status_fails_closed(status: str) -> None:
    resolution = resolve_ingestion_idempotency_replay(_job(status=status))

    assert resolution.disposition is IngestionIdempotencyReplayDisposition.FAILED
    assert resolution.status_code == 500
    assert resolution.detail == {
        "code": "INGESTION_REPLAY_STATE_INVALID",
        "message": "The stored ingestion job state is not recognized.",
        "job_id": "ing_job_001",
        "status": status,
    }
