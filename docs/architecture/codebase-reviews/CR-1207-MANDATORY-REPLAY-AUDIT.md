# CR-1207: Mandatory Replay Audit

Date: 2026-06-30

## Objective

Address GitHub issue #555 by removing the best-effort replay-audit path from ingestion retry and
consumer-DLQ replay workflows. Privileged replay decisions must either produce durable replay audit
evidence or fail with a governed API response that does not acknowledge the replay outcome.

## Expected Improvement

Replay, dry-run, duplicate-block, not-replayable, publish-failure, and post-publish bookkeeping
failure paths now share one mandatory audit recording helper. Audit-store failures are mapped to
`INGESTION_REPLAY_AUDIT_WRITE_FAILED` with source-safe recovery context, preventing successful or
bookkeeping-failure responses with `replay_audit_id = null`.

## Implementation

1. Replaced `_record_replay_audit_best_effort(...)` with `_record_mandatory_replay_audit(...)`.
2. Routed ingestion-job retry audits and consumer-DLQ replay audits through the mandatory helper.
3. Preserved existing `INGESTION_RETRY_BOOKKEEPING_FAILED` and
   `INGESTION_DLQ_REPLAY_BOOKKEEPING_FAILED` behavior when `replayed_bookkeeping_failed` audit
   evidence is successfully recorded.
4. Added `INGESTION_REPLAY_AUDIT_WRITE_FAILED` response metadata to affected OpenAPI contracts.
5. Added route-level tests for audit-write failure before publish (`dry_run`) and after publish
   when bookkeeping failure audit recording fails.

## Tests Added

1. Mandatory replay-audit helper success and governed-failure unit coverage.
2. Ingestion retry success-audit failure coverage proving audit failure is not misclassified as
   bookkeeping success.
3. Duplicate-block audit failure coverage.
4. Consumer-DLQ replay success-audit failure coverage.
5. Route-level dry-run audit-write failure coverage.
6. Route-level post-publish bookkeeping audit-write failure coverage.
7. OpenAPI assertions for the new audit-write-failure examples.

## Validation Evidence

Focused checks run locally:

```powershell
python -m pytest tests/unit/services/event_replay_service/test_ingestion_operations.py -q
```

Result: `19 passed`.

```powershell
python -m pytest tests/integration/services/ingestion_service/test_ingestion_routers.py::test_replay_consumer_dlq_event_reports_audit_write_failure_for_dry_run tests/integration/services/ingestion_service/test_ingestion_routers.py::test_replay_consumer_dlq_event_reports_audit_write_failure_after_publish tests/integration/services/ingestion_service/test_ingestion_routers.py::test_replay_consumer_dlq_event_reports_bookkeeping_failure_after_publish -q
```

Result: `3 passed`.

```powershell
python -m pytest tests/integration/services/event_replay_service/test_event_replay_app.py::test_openapi_describes_event_replay_operational_parameters -q
```

Result: `1 passed`.

## Compatibility Impact

Existing successful replay, dry-run, duplicate-block, publish-failure, and bookkeeping-failure
statuses are preserved when replay audit persistence succeeds. The intentional behavior change is
that audit persistence failure no longer produces a successful or bookkeeping-failure response with
a null audit id. Clients now receive `500 INGESTION_REPLAY_AUDIT_WRITE_FAILED` and must treat the
replay outcome as unacknowledged.

## Documentation And Wiki

Updated operations guidance, codebase review ledger, quality scorecard, and refactor health report.
No repo-local wiki change is required because the affected operator guidance is maintained in
repo-local operations docs, not a separate authored wiki page.

## Follow-Up

Issue #555 remains open for PR, GitHub CI, QA validation, and any future decision to persist a
separate audit-failure recovery table when the replay-audit store itself is unavailable.
