# CR-1206: DLQ Correlation Diagnostics

Date: 2026-06-30

## Objective

Address GitHub issue #556 by ensuring consumer DLQ and replay-audit records either carry a
`correlation_id` or expose an explicit `correlation_missing_reason` with a durable
`alternate_lookup_key`.

## Expected Improvement

Operators can now diagnose and audit DLQ replay attempts when legacy or malformed events lack
correlation metadata. The reusable pattern is additive across the shared Kafka DLQ writer, DLQ read
mapper, replay response DTOs, and replay-audit persistence path, so future replay routes can reuse
the same correlation-or-reason contract.

The slice also hardens CI reliability by making the ingestion write rate-limit Prometheus counter
registration idempotent. This prevents duplicate metric registration when integration tests import
multiple service apps in one Python process.

## Implementation

1. Added nullable `correlation_missing_reason` and `alternate_lookup_key` columns to
   `consumer_dlq_events` and `consumer_dlq_replay_audit`.
2. Added a forward Alembic migration with legacy backfill and support indexes on alternate lookup
   keys.
3. Updated shared Kafka DLQ persistence to write missing-correlation diagnostics when no
   correlation id is present.
4. Updated DLQ event, replay response, and replay-audit DTOs to expose the diagnostics
   additively.
5. Updated consumer-DLQ replay not-replayable handling to record and return the missing-correlation
   reason and alternate lookup key.
6. Made ingestion write rate-limit counter registration idempotent to avoid collection-time
   duplicate Prometheus metric failures.

## Tests Added

1. DLQ event mapper coverage for legacy rows without correlation metadata.
2. Kafka consumer DLQ persistence coverage for missing-correlation diagnostics.
3. Replay-audit persistence coverage for missing-correlation diagnostics.
4. Event-replay helper coverage proving not-replayable responses propagate diagnostics.
5. Ops-controls coverage proving the rate-limit counter factory is idempotent.
6. Integration coverage updated for the missing-correlation replay response body.

## Validation Evidence

Focused checks run locally:

```powershell
python -m pytest tests/unit/libs/portfolio-common/test_kafka_consumer.py::test_record_consumer_dlq_event_redacts_payload_excerpt tests/unit/libs/portfolio-common/test_kafka_consumer.py::test_record_consumer_dlq_event_persists_missing_correlation_diagnostics tests/unit/services/ingestion_service/services/test_ingestion_consumer_dlq_events.py tests/unit/services/ingestion_service/services/test_ingestion_replay_audits.py tests/unit/services/event_replay_service/test_ingestion_operations.py -q
```

Result: `26 passed`.

```powershell
python -m pytest tests/unit/services/ingestion_service/test_ops_controls.py -q
```

Result: `13 passed`.

```powershell
python -m pytest tests/integration/services/ingestion_service/test_ingestion_routers.py::test_replay_consumer_dlq_event_reports_not_replayable_without_correlation tests/integration/services/event_replay_service/test_event_replay_app.py::test_openapi_describes_event_replay_shared_schema_depth tests/integration/services/event_replay_service/test_event_replay_app.py::test_openapi_describes_event_replay_operational_parameters -q
```

Result: `3 passed`.

## Compatibility Impact

The API and schema changes are additive. Existing nullable `correlation_id` behavior is preserved,
legacy rows are backfilled where possible, and response consumers continue receiving the prior
fields. New consumers can use `correlation_missing_reason` and `alternate_lookup_key` for support
lookups when correlation is absent.

## Documentation And Wiki

Updated repository-local architecture, schema catalog, quality scorecard, refactor health report,
and repository context. No repo-local wiki change is required because this slice changes API/schema
diagnostic truth and CI import reliability, not an operator command or published wiki runbook.

## Follow-Up

Issue #556 remains open for PR, GitHub CI, QA validation, and broader correlation-or-reason
coverage across other durable operational records such as processed events, outbox events,
valuation jobs, aggregation jobs, and reprocessing jobs.
