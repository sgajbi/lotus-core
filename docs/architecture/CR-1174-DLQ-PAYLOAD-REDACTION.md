# CR-1174 DLQ Payload Redaction

## Objective

Begin GitHub issue #497 by protecting shared Kafka consumer DLQ payloads, headers, error text, and
persisted DLQ evidence from sensitive-data overexposure.

## Expected Improvement

- DLQ Kafka messages no longer carry raw sensitive payload keys when those keys match the shared
  redaction policy.
- Copied Kafka headers redact authorization, token, credential, password, secret, database URL, and
  connection-string header values before DLQ publication.
- Persisted consumer DLQ evidence stores redacted payload excerpts and redacted error reasons.
- Operator-facing schema text now identifies `payload_excerpt` as redacted diagnostic evidence.

## Changes

- Reused `portfolio_common.logging_utils.redact_sensitive(...)` and `redact_sensitive_text(...)`
  from the shared redaction layer added in CR-1173.
- Added shared Kafka consumer helpers for JSON payload redaction, raw-text fallback redaction, and
  sensitive DLQ header masking.
- Routed DLQ payload `original_value`, `error_reason`, `error_traceback`, copied headers,
  persisted `ConsumerDlqEvent.error_reason`, and persisted `payload_excerpt` through the redaction
  boundary.
- Updated the consumer DLQ response DTO description to identify `payload_excerpt` as redacted and
  truncated.
- Updated repo-local Event Replay Service wiki source with the operator handling note.

## Compatibility

Kafka DLQ payload shape, DLQ header names, database schema, API route shape, response fields, and
replay contracts are unchanged. Values change intentionally only where sensitive keys or
credential-bearing text are present. Existing non-sensitive JSON payload text remains byte-for-byte
compatible to avoid unnecessary downstream replay-diagnostic churn.

## Retention And Access-Control Posture

This slice does not change physical retention or authorization policy. Consumer DLQ events remain
operator/control-plane evidence and should stay behind the existing protected event-replay service
access boundary. Redaction reduces accidental overexposure, but DLQ evidence can still contain
client-linked identifiers such as portfolio IDs or transaction IDs and must not be treated as a
public or front-office data contract.

## Validation

- `python -m pytest tests/unit/libs/portfolio-common/test_kafka_consumer.py -q`
- `python -m pytest tests/integration/services/event_replay_service/test_event_replay_app.py::test_ingestion_operations_openapi_schema_carries_operational_metadata -q`
- `python -m ruff check src/libs/portfolio-common/portfolio_common/kafka_consumer.py src/services/ingestion_service/app/DTOs/ingestion_job_replay_dto.py tests/unit/libs/portfolio-common/test_kafka_consumer.py tests/integration/services/event_replay_service/test_event_replay_app.py`
- `python -m ruff format --check src/libs/portfolio-common/portfolio_common/kafka_consumer.py src/services/ingestion_service/app/DTOs/ingestion_job_replay_dto.py tests/unit/libs/portfolio-common/test_kafka_consumer.py tests/integration/services/event_replay_service/test_event_replay_app.py`

## Documentation And Wiki Decision

Updated this ledger entry, the quality scorecard/health report, and the repo-local Event Replay
Service wiki source. No generated OpenAPI artifact is committed in this slice; the focused schema
test pins the DTO description change.

## Follow-Up

Issue #497 remains open pending PR, GitHub CI, and QA evidence. Broader follow-up should validate
DLQ/replay authorization gates and review any service-specific replay payload stores that bypass
the shared `BaseConsumer` DLQ path.
