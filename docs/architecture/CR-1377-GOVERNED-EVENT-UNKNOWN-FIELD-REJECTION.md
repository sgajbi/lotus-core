# CR-1377 Governed Event Unknown Field Rejection

Date: 2026-07-05

## Objective

Fix GitHub issue #558 by ensuring governed event payloads cannot silently drop unknown fields such
as future lineage, schema, source, or audit metadata.

## Change

- Verified the shared `CoreEventModel` uses `extra="forbid"` so unknown governed event fields are
  rejected instead of ignored.
- Added an all-subclass regression test proving every governed `CoreEventModel` event rejects
  unknown payload fields with source-safe validation errors.
- Reused existing DLQ validation/redaction tests as evidence that consumer-side validation failures
  preserve delivery/correlation diagnostics without leaking rejected sensitive values.

## Expected Improvement

Producer/consumer contract drift is now fail-fast for every governed event model rather than only a
single representative transaction event. This prevents future lineage/audit metadata from being
silently discarded and makes unknown-field drift observable through existing validation and DLQ
paths.

## Tests Added Or Updated

- Updated `tests/unit/libs/portfolio-common/test_events.py` with
  `test_all_core_event_models_reject_unknown_payload_fields`.

## Validation Evidence

- `python -m pytest tests/unit/libs/portfolio-common/test_events.py -q`
  - Result: 11 passed.
- `python -m pytest tests/unit/libs/portfolio-common/test_kafka_consumer.py::test_dlq_validation_error_reason_omits_rejected_input_value tests/unit/libs/portfolio-common/test_kafka_consumer.py::test_record_consumer_dlq_event_redacts_payload_excerpt tests/unit/libs/portfolio-common/test_kafka_consumer.py::test_record_consumer_dlq_event_persists_missing_correlation_diagnostics tests/unit/libs/portfolio-common/test_kafka_consumer.py::test_record_consumer_dlq_event_uses_source_safe_validation_reason tests/unit/libs/portfolio-common/test_event_supportability.py -q`
  - Result: 23 passed.
- `python -m ruff check tests/unit/libs/portfolio-common/test_events.py`
  - Result: passed.
- `python -m ruff format --check tests/unit/libs/portfolio-common/test_events.py`
  - Result: passed.
- `make quality-wiki-docs-gate`
  - Result: passed.
- `make architecture-guard`
  - Result: passed.
- `git diff --check`
  - Result: passed.

## Compatibility

Existing valid event payloads remain compatible. The intended behavior for unknown governed event
fields is fail-fast validation with source-safe error evidence rather than silent field dropping.
No topic, schema field, database table, public API, or runtime topology changed in this slice.

## Same-Pattern Scan

`CoreEventModel.__subclasses__()` now has a regression test that covers all current governed event
models, not just `TransactionEvent`. Existing Kafka consumer DLQ tests cover validation reason
redaction, payload excerpt redaction, and missing-correlation diagnostics.

## Documentation And Wiki Decision

Repository context and the codebase review ledger are updated in this slice. No wiki source change
is required because no operator command, public API, or supported feature description changed.

No platform skill change is required: the existing backend governance already requires event
contract drift to be tested and support-safe. The durable repo-specific rule belongs in
`REPOSITORY-ENGINEERING-CONTEXT.md`.
