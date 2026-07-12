# CR-1260 Ingestion Bookkeeping Repair Boundary

Date: 2026-07-01

## Scope

Continue GitHub issue #446 by reducing the final measured B-ranked helper in the event replay
ingestion operations route.

## Finding

Issue #446 remains valid. CR-1167 reduced replay publish dispatch and CR-1168 reduced consumer-DLQ
replay candidate selection, but `repair_ingestion_job_bookkeeping(...)` still mixed job lookup,
failure-evidence eligibility, accepted-to-queued repair mutation, failed-repair error mapping, and
operator response assembly in the API route handler.

## Action Taken

Extracted focused helpers for:

1. required ingestion job lookup and governed 404 mapping,
2. bookkeeping failure-phase eligibility and governed 409 mapping,
3. accepted-job queue repair mutation and governed 500 mapping,
4. repair response assembly and supportability reason-code mapping.

The public route remains a thin HTTP adapter that orchestrates the existing service calls and
returns the same `IngestionJobBookkeepingRepairResponse` contract.

This is an in-process design-boundary improvement only. It does not introduce a new runtime
service.

## Compatibility

No API route, OpenAPI response shape, response DTO, database schema, Kafka topic, source-data
product, authorization policy, metric, or downstream contract changed. Existing repair behavior is
preserved:

1. missing jobs still return `404 INGESTION_JOB_NOT_FOUND`,
2. jobs without bookkeeping-failure evidence or in ineligible statuses still return
   `409 INGESTION_BOOKKEEPING_REPAIR_NOT_ELIGIBLE`,
3. accepted jobs still call `mark_queued(...)`,
4. queued jobs remain eligible without an extra queue mutation,
5. failed queue mutation still returns `500 INGESTION_BOOKKEEPING_REPAIR_FAILED`,
6. supportability reason codes still come from the existing bookkeeping recovery vocabulary.

## Tests Added

Extended `tests/unit/services/event_replay_service/test_ingestion_operations.py` with direct tests
for the extracted bookkeeping repair helpers:

1. missing-job error mapping,
2. eligible and ineligible failure-phase/status policy,
3. governed mark-queued failure mapping,
4. response supportability reason-code assembly.

## Validation

Focused behavior proof:

- `python -m pytest tests\unit\services\event_replay_service\test_ingestion_operations.py tests\integration\services\event_replay_service\test_event_replay_app.py -q`
- Result: `41 passed`

Static proof:

- `python -m ruff check src\services\event_replay_service\app\routers\ingestion_operations.py tests\unit\services\event_replay_service\test_ingestion_operations.py`
- Result: passed
- `python -m ruff format --check src\services\event_replay_service\app\routers\ingestion_operations.py tests\unit\services\event_replay_service\test_ingestion_operations.py`
- Result: `2 files already formatted`

Measured quality proof:

- `python -m radon cc src\services\event_replay_service\app\routers\ingestion_operations.py -s -a`
- Result: `repair_ingestion_job_bookkeeping` is now `A (3)` and all functions in the module are
  A-ranked by cyclomatic complexity.
- `python -m radon mi src\services\event_replay_service\app\routers\ingestion_operations.py -s`
- Result: module maintainability remains `B (12.86)`.

## Residual Issue Scope

This completes the measured function-level hotspot sequence that #446 identified across replay
publish dispatch, consumer-DLQ replay candidate selection, and bookkeeping repair response
assembly. The route file remains large and `B`-ranked by maintainability, so future work should
continue extracting cohesive retry payload, job field normalization, and operator-response
boundaries only when each slice preserves behavior with focused tests.

## Documentation And Wiki Decision

Updated the codebase review ledger, quality scorecard, and refactor health report. No README or
wiki source update is required because this slice changes internal helper boundaries only and does
not change operator commands, public API contracts, supported features, or runbook truth.

Wiki publication check:

- `..\lotus-platform\automation\Sync-RepoWikis.ps1 -CheckOnly -Repository lotus-core`
- Result: failed on pre-existing published-wiki drift for `Data-Models.md`,
  `Mesh-Data-Products.md`, `Operations-Runbook.md`, and `Outbox-Events.md`; no repo-local wiki
  source page changed in CR-1260.

## Bank-Buyable Control Movement

This slice improves:

1. API adapter thinness for an operator-facing repair route,
2. testability of failure eligibility and response assembly,
3. measured complexity posture by removing the final B-ranked function from the route module,
4. future agent guardrails by documenting the remaining maintainability boundary honestly.
