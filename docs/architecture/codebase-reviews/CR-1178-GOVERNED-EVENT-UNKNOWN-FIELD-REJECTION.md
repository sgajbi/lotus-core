# CR-1178 Governed Event Unknown Field Rejection

## Objective

Address GitHub issue #558 by preventing governed event payloads from silently dropping unknown
fields during shared Pydantic validation.

## Expected Improvement

- Governed event models now reject unknown payload fields with `extra_forbidden` validation errors
  while preserving the explicit outbox envelope metadata fields.
- Persistence and calculator consumers that validate through shared event models can route producer
  drift to the existing poison-message and DLQ path instead of processing a truncated payload.
- Kafka DLQ payloads and persisted consumer DLQ audit rows summarize Pydantic validation errors
  without raw rejected input values.
- Existing valid event payloads keep the same fields, normalization, and downstream model contracts.

## Changes

- Changed `CoreEventModel` from `extra="ignore"` to `extra="forbid"`.
- Added explicit shared event-envelope fields for `event_type`, `schema_version`, and
  `correlation_id`.
- Added source-safe validation-error summaries in the shared Kafka consumer DLQ path.
- Added contract tests proving `TransactionEvent` rejects an unknown `event_version` field.
- Added DLQ tests proving rejected unknown-field values are omitted from error reason and traceback
  evidence while original payload excerpts remain redacted by the shared sensitivity policy.

## Compatibility

This intentionally changes invalid/drifted event behavior only. Existing valid event payloads,
outbox-enriched payloads, Kafka topics, database schema, OpenAPI routes, and emitted field names are
unchanged. Producers that previously sent undeclared governed event fields will now fail validation
and use DLQ recovery instead of being accepted with fields silently removed.

## Validation

- `python -m pytest tests/unit/libs/portfolio-common/test_events.py tests/unit/libs/portfolio-common/test_kafka_consumer.py -q`
- `python -m ruff check src/libs/portfolio-common/portfolio_common/events.py src/libs/portfolio-common/portfolio_common/kafka_consumer.py tests/unit/libs/portfolio-common/test_events.py tests/unit/libs/portfolio-common/test_kafka_consumer.py`
- `python -m ruff format --check src/libs/portfolio-common/portfolio_common/events.py src/libs/portfolio-common/portfolio_common/kafka_consumer.py tests/unit/libs/portfolio-common/test_events.py tests/unit/libs/portfolio-common/test_kafka_consumer.py`

## Documentation And Wiki Decision

Updated this ledger entry, the quality scorecard/health report, and repo-local Outbox/Event Replay
wiki sources because event contract and DLQ operator truth changed.

## Follow-Up

Issue #558 remains open pending PR review, GitHub CI, QA evidence, and broader event-envelope
governance for explicit versioning, correlation, causation, idempotency, and lineage metadata.
