# CR-1228 Post-Publish Bookkeeping Repair

Date: 2026-07-01

## Objective

Fix GitHub issue #595 by making direct ingestion post-publish and post-persist bookkeeping failures
explicit, client-safe, and repairable. The slice promotes the platform pattern that partial-failure
boundaries must distinguish completed publish/persist work from failed metadata bookkeeping.

## Change

- Added shared ingestion bookkeeping recovery vocabulary in
  `src/services/ingestion_service/app/bookkeeping_recovery.py`.
- Expanded `INGESTION_JOB_BOOKKEEPING_FAILED` details with `publish_state`, `work_state`,
  `published_record_count`, `retry_safe`, `recovery_action`, `recovery_path`,
  `supportability_reason_code`, and source-safe remediation guidance.
- Passed accepted/published counts from direct ingestion routers into the shared bookkeeping
  failure helper.
- Distinguished reference-data persistence failures from publish failures using
  `publish_state="not_published"` and `work_state="persisted"`.
- Added protected `POST /ingestion/jobs/{job_id}/bookkeeping/repair` on the event-replay
  operations surface. The command only repairs jobs with recorded `queue_bookkeeping` or
  `persist_bookkeeping` failure evidence and rejects blind repair attempts.
- Added `IngestionJobBookkeepingRepairResponse` as the operator repair response DTO.

## Expected Improvement

Clients no longer receive a generic 500 that can be misread as publish failure after publish or
persist work completed. Operators get an explicit non-retry-safe response and a governed repair
path that can move an accepted job to queued after failure-history evidence confirms the partial
failure.

## Tests Added

- Unit coverage for the enriched `INGESTION_JOB_BOOKKEEPING_FAILED` detail shape.
- Unit coverage that post-publish failures report `published` state and record count.
- Integration coverage that transaction post-publish bookkeeping failure reports publish state,
  retry safety, reason code, and can be repaired through the protected operations endpoint.
- Integration coverage that reference-data post-persist bookkeeping failure reports persisted
  state and can be repaired through the protected operations endpoint.
- Integration coverage that bookkeeping repair rejects jobs without bookkeeping-failure evidence.
- OpenAPI coverage for the new protected repair endpoint.

## Validation Evidence

- Focused helper and OpenAPI tests passed:
  `python -m pytest tests\unit\services\ingestion_service\routers\test_job_bookkeeping.py tests\integration\services\event_replay_service\test_event_replay_app.py -q`.
- Focused bookkeeping integration tests passed:
  `python -m pytest tests\integration\services\ingestion_service\test_ingestion_routers.py -q -k "bookkeeping"`.
- Combined focused selection passed:
  `python -m pytest tests\unit\services\ingestion_service\routers\test_job_bookkeeping.py tests\integration\services\event_replay_service\test_event_replay_app.py tests\integration\services\ingestion_service\test_ingestion_routers.py -q -k "bookkeeping or event_replay_openapi"`.
- Scoped Ruff lint passed for touched source and test files.
- Scoped Ruff format check passed for touched source and test files.
- Type checking passed:
  `make typecheck`.

- Route contract-family guard passed after registering the new repair route:
  `make route-contract-family-guard`.
- Route contract-family guard unit tests passed:
  `python -m pytest tests\unit\scripts\test_route_contract_family_guard.py -q`.
- Repository lint gate passed:
  `make lint`.
- OpenAPI gate passed:
  `make openapi-gate`.
- API vocabulary gate passed:
  `make api-vocabulary-gate`.
- Wiki/documentation gate passed:
  `make quality-wiki-docs-gate`.
- Whitespace diff check passed:
  `git diff --check`.

## Downstream Compatibility

The existing direct ingestion route paths, success DTOs, HTTP 500 status for bookkeeping failure,
and `INGESTION_JOB_BOOKKEEPING_FAILED` code are preserved. The intentional contract expansion is
additional failure-detail fields and the new protected operator repair endpoint.

The primary client message no longer embeds raw bookkeeping exception text. Detailed failure
evidence remains durable in ingestion job failure history.

No database schema, Kafka topic, or ingestion success response changed.

## Documentation And Wiki Decision

Updated this architecture record, codebase review ledger, operations runbook, repository context,
quality scorecard, and refactor health report. No repo-local wiki update is required because the
operator-facing repair path is summarized in `docs/operations-runbook.md` and the protected API is
documented in OpenAPI.

## Remaining Follow-Up

- Keep issue #595 open for PR/CI/QA evidence and Docker-backed proof against the real database and
  Kafka-backed ingestion stack.
- Apply the same evidence-gated repair pattern to adjacent partial-failure operator workflows
  through issue-backed slices.
