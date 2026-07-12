# CR-1247 Async Traceparent Propagation

Date: 2026-07-01

## Objective

Fix GitHub issue #493 by propagating W3C `traceparent` context across Lotus Core's async event
paths instead of stopping trace evidence at HTTP request handling.

## Change

- Added shared trace helpers and `traceparent_var` to `portfolio_common.logging_utils`.
- Updated standard HTTP bootstrap to preserve an incoming valid `traceparent`, derive `X-Trace-Id`
  from it, and store both `trace_id` and `traceparent` in request context.
- Extended the governed event envelope with additive `traceparent` metadata.
- Updated outbox creation and dispatch so outbox payloads carry `traceparent` and dispatched Kafka
  records include a `traceparent` header.
- Updated shared Kafka consumers so message processing and DLQ publication preserve traceparent
  context.
- Updated direct ingestion Kafka publication and DLQ replay to preserve `traceparent` headers.

## Expected Improvement

Operators can correlate incidents from HTTP ingestion through outbox dispatch, Kafka consumers,
consumer DLQ, and replay paths using standard W3C trace context plus the existing Lotus
`correlation_id`. The change promotes one reusable async lineage pattern instead of service-local
trace header handling.

## Tests Added Or Updated

- HTTP bootstrap test for incoming `traceparent` preservation.
- Outbox repository tests for `traceparent` envelope capture and conflict rejection.
- Event model/supportability tests proving strict event models accept governed `traceparent`
  metadata.
- Outbox dispatcher DB-backed test proving `traceparent` becomes a Kafka header.
- Kafka consumer tests for traceparent context and DLQ payload/header propagation.
- Ingestion service test proving direct publish headers include `traceparent`.
- DLQ replay integration test proving replay republishes `traceparent`.

## Validation Evidence

- Focused unit suite passed:
  `python -m pytest tests\unit\libs\portfolio-common\test_outbox_repository.py tests\unit\libs\portfolio-common\test_events.py tests\unit\libs\portfolio-common\test_event_supportability.py tests\unit\libs\portfolio-common\test_kafka_consumer.py tests\unit\libs\portfolio-common\test_http_app_bootstrap.py tests\unit\services\ingestion_service\services\test_ingestion_service.py -q --tb=short`
  -> 99 passed.
- DB-backed outbox dispatcher propagation proof passed:
  `python -m pytest tests\integration\libs\portfolio-common\test_outbox_dispatcher.py::test_dispatcher_propagates_correlation_id_and_traceparent -q --tb=short`
  -> 1 passed.
- DLQ replay integration proof passed:
  `python -m pytest tests\integration\tools\test_dlq_replayer.py::test_dlq_replayer_consumes_and_republishes -q --tb=short`
  -> 1 passed.
- Scoped Ruff lint and format checks passed for touched source/test files.
- `make typecheck` passed.

## Downstream Compatibility

This is an additive event metadata and Kafka-header change. Existing `correlation_id` behavior,
event type names, schema version, Kafka topics, business payload fields, and API routes are
preserved. Strict governed event models now explicitly accept `traceparent` as envelope metadata;
unknown non-governed fields remain rejected.

## Documentation And Wiki Decision

Updated this architecture record, the codebase review ledger, RFC-0083 eventing supportability
target model, repository context, and quality/refactor scorecards because async event contract truth
changed. No wiki change is required because no operator command or runbook procedure changed.

## Remaining Follow-Up

- Add a future guard/inventory field for direct Kafka topic `traceparent` header support if direct
  publish coverage expands beyond current focused tests.
