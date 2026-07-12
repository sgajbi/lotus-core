# CR-1271: Bot Review PR Hardening

## Objective

Close the actionable PR #695 Codex review threads without weakening branch protection or bypassing required conversation resolution.

## Findings

The review identified five valid P2 defects:

- Kafka optional `traceparent` header decoding could raise on non-UTF-8 bytes before invalid trace context was treated as absent.
- Kafka failure-budget keys decoded binary message keys as UTF-8, turning retryable/DLQ failures into critical consumer-loop exits.
- Bulk upload reads materialized the full multipart file before enforcing `LOTUS_CORE_INGEST_UPLOAD_MAX_BYTES`.
- The generic enterprise write payload cap could reject governed upload routes before the upload-specific budget was applied.
- Transaction persistence could leak transport envelope `traceparent` into table insert values.

## Actions

- Added bytes-safe Kafka header/key helpers; invalid `traceparent` bytes now normalize to absent, while binary keys use deterministic `hex:` text.
- Filtered raw incoming `traceparent` headers out of DLQ headers and reattached only normalized valid trace context.
- Added a reusable enterprise middleware write-budget resolver and wired ingestion upload routes to their governed upload budget with bounded multipart overhead.
- Streamed upload bodies in 64 KiB chunks and fail-fast once the configured file byte limit is exceeded.
- Routed transaction persistence mapping through `event_business_payload(...)` and retained existing transaction-table-only exclusions.

## Compatibility

No route path, OpenAPI response contract, Kafka topic, database schema, DLQ payload field name, transaction table column, auth policy, README, or wiki behavior changed. The fixes preserve existing valid traceparent propagation, valid UTF-8 Kafka keys, governed upload limits, and transaction persistence behavior while closing failure modes for malformed bytes and oversized uploads.

No wiki update required: this slice corrects implementation behavior behind existing operator-facing limits and does not change commands, supported features, or runbook truth.

## Validation

- `python -m pytest tests/unit/libs/portfolio-common/test_kafka_consumer.py tests/unit/services/persistence_service/repositories/test_transaction_db_repository.py -q` -> 61 passed.
- `python -m pytest tests/integration/services/ingestion_service/test_ingestion_routers.py -q -k "upload_preview_rejects_payload_above_configured_limit or upload_preview_allows_upload_budget_above_generic_write_cap or read_bounded_upload_content_stops_after_stream_exceeds_limit"` -> 3 passed, 215 deselected.
- `python -m ruff check` on touched source/tests -> passed.
- `python -m ruff format --check` on touched source/tests -> passed.
