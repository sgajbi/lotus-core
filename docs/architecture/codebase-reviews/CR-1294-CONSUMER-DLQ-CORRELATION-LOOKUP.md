# CR-1294 Consumer DLQ Correlation Lookup

## Scope

Issue cluster: GitHub issue #700.

This slice removes the consumer-DLQ replay dependency on generic ingestion-job list paging and
adds a dedicated indexed lookup for correlated replayable ingestion jobs.

## Objective

Reduce runtime complexity and recovery fragility by making consumer-DLQ replay resolve its
correlated ingestion job through a purpose-built query instead of scanning the newest 500 operator
list rows in memory.

## Changes

1. Added `load_latest_replayable_job_by_correlation_id(...)` and a query builder that filters by
   correlation id and replayable statuses, then orders by descending database id for deterministic
   duplicate-correlation handling.
2. Exposed the lookup through `IngestionJobService`.
3. Rewired `ConsumerDlqReplayCommandService` to use the lookup instead of `list_jobs(limit=500)`.
4. Added a composite `ingestion_jobs(correlation_id, status, id DESC)` index in the SQLAlchemy
   model and Alembic migration.
5. Updated command and ingestion-service tests to prove the command no longer calls the generic
   list API and the query shape is correlation/status/id ordered.

## Behavior And Compatibility

Operator/API response contracts are unchanged. Route paths, status codes, response DTOs, replay
audit fields, replay fingerprints, missing-correlation handling, missing-payload handling, dry-run
behavior, and publish behavior are unchanged.

The intentional behavior improvement is that a valid correlated DLQ event can resolve its
ingestion job regardless of unrelated ingestion-job volume. If duplicate correlation ids exist, the
latest replayable row by database id is selected deterministically.

## Validation Evidence

Focused local validation:

1. `python -m pytest tests\unit\services\ingestion_service\services\test_ingestion_job_listing.py tests\unit\services\event_replay_service\test_consumer_dlq_replay_commands.py`
   - 15 passed.
2. `python -m ruff check src\services\ingestion_service\app\services\ingestion_job_listing.py src\services\ingestion_service\app\services\ingestion_job_service.py src\services\event_replay_service\app\application\consumer_dlq_replay_commands.py src\libs\portfolio-common\portfolio_common\database_models.py tests\unit\services\ingestion_service\services\test_ingestion_job_listing.py tests\unit\services\event_replay_service\test_consumer_dlq_replay_commands.py alembic\versions\c100a1b2c3d4_perf_add_ingestion_job_correlation_lookup_index.py`
   - passed.
3. `python -m ruff format --check src\services\ingestion_service\app\services\ingestion_job_listing.py src\services\ingestion_service\app\services\ingestion_job_service.py src\services\event_replay_service\app\application\consumer_dlq_replay_commands.py src\libs\portfolio-common\portfolio_common\database_models.py tests\unit\services\ingestion_service\services\test_ingestion_job_listing.py tests\unit\services\event_replay_service\test_consumer_dlq_replay_commands.py alembic\versions\c100a1b2c3d4_perf_add_ingestion_job_correlation_lookup_index.py`
   - passed.
4. `python -m alembic heads`
   - single head: `c100a1b2c3d4`.
5. `$env:DATABASE_URL='sqlite:///migration-smoke.db'; python -m alembic upgrade c1009d0e1f2a3:c100a1b2c3d4 --sql`
   - rendered `CREATE INDEX ix_ingestion_jobs_correlation_status_id ON ingestion_jobs (correlation_id, status, id DESC);`.
6. `make quality-wiki-docs-gate`
   - passed.
7. `python C:\Users\Sandeep\.codex\skills\lotus-readme-wiki-governance\scripts\audit_wiki_quality.py --wiki-dir wiki`
   - passed.
8. `git diff --check`
   - passed with CRLF normalization warnings only.
9. `powershell -ExecutionPolicy Bypass -File C:\Users\Sandeep\projects\lotus-platform\automation\Sync-RepoWikis.ps1 -CheckOnly -Repository lotus-core`
   - reported expected pre-merge published-wiki drift for authored pages including
     `Event-Replay-Service.md`; publish after merge remains required.

## Documentation, Wiki, Context, And Skill Decision

Updated repo context and the Event Replay wiki source with the durable rule that replay recovery
joins must use purpose-built lookup methods instead of operator listing pages.

No central Lotus skill change is required. The existing backend delivery and codebase review
ledger guidance already covers issue-driven adjacent-pattern scans and runtime/design complexity
reductions.

## Remaining Work

Continue with issue #701 to protect ingestion job lifecycle transitions with expected-state
guards. This slice intentionally does not change lifecycle state-machine semantics.
