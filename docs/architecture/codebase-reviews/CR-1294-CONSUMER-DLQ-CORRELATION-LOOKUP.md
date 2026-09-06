# CR-1294 Consumer DLQ Correlation Lookup

## Scope

Issue cluster: GitHub issues #700, #862, and #863.

This slice removes the consumer-DLQ replay dependency on generic ingestion-job list paging and
adds a dedicated indexed lookup for correlated replayable ingestion jobs.

## 2026-07-31 Ownership And Recovery Correction

The original #700 implementation removed an unbounded operator-list scan, but its
latest-by-correlation rule still conflated trace identity with durable workflow ownership. Issues
#862 and #863 supersede that rule:

1. job-backed ingestion and replay publish `ingestion_job_id`;
2. consumer context, outbox persistence/dispatch, and DLQ persistence preserve that owner;
3. evidence bundles query DLQ rows by indexed `ingestion_job_id`, with exact replay-event linking
   retained for missing original correlation;
4. legacy ownerless rows use the bounded correlation lookup only when exactly one replayable job
   matches; ambiguous reuse remains unmapped and fail closed;
5. replay audit reads are ordered by `(requested_at DESC, id DESC)` and folded independently per
   DLQ event;
6. `replayed` clears that event, while later equivalent `duplicate_blocked` preserves recovery only
   with older durable success. Later failure, bookkeeping failure, dry-run-only history, or
   truncated evidence remains unresolved.

Migration `c133b2c3d506` backfills legacy DLQ ownership only for correlation identifiers that map to
exactly one ingestion job, adds the DLQ ownership foreign key and covering index, retains ownership
on outbox rows, and adds deterministic job-scoped replay-audit ordering support.

## Objective

Reduce runtime complexity and recovery fragility by making consumer-DLQ replay resolve its
correlated ingestion job through a purpose-built query instead of scanning the newest 500 operator
list rows in memory.

## Original #700 Changes

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

The original improvement allowed a valid correlated DLQ event to resolve its ingestion job
regardless of unrelated ingestion-job volume. The 2026-07-31 correction intentionally removes
latest-row selection: durable owner identity wins, while ambiguous legacy correlation fails closed.

## Validation Evidence

2026-07-31 correction evidence:

1. 217 focused unit tests passed across recovery policy, ownership propagation, replay commands,
   evidence queries, stores, publishers, consumers, outbox, and migration contracts.
2. PostgreSQL migration round-trip passed, proving unique-correlation backfill,
   ambiguous-correlation isolation, foreign-key enforcement, covering indexes, downgrade, and
   reapply.
3. `make migration-smoke` passed with single head `c133b2c3d506`.

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
7. `python ../lotus-platform/codex/skills/lotus-readme-wiki-governance/scripts/audit_wiki_quality.py --wiki-dir wiki`
   - passed.
8. `git diff --check`
   - passed with CRLF normalization warnings only.
9. `powershell -ExecutionPolicy Bypass -File ../lotus-platform/automation/Sync-RepoWikis.ps1 -CheckOnly -Repository lotus-core`
   - reported expected pre-merge published-wiki drift for authored pages including
     `Event-Replay-Service.md`; publish after merge remains required.

## Documentation, Wiki, Context, And Skill Decision

Updated repo context and the Event Replay wiki source with the durable rule that replay recovery
joins must use purpose-built lookup methods instead of operator listing pages.

No central Lotus skill change is required. The existing backend delivery and codebase review
ledger guidance already covers issue-driven adjacent-pattern scans and runtime/design complexity
reductions.

## Remaining Work

No actionable #862/#863 defect remains locally. Protected PR CI, exact-main validation, wiki
publication, issue evidence, and verified closure remain delivery steps rather than implementation
gaps. Lifecycle transition compare-and-set work remains independently governed by its own issue.
