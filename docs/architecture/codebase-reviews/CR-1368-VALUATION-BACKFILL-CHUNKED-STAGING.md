# CR-1368 Valuation Backfill Chunked Staging

## Objective

Fix GitHub issue #579 by replacing per-state valuation backfill upserts with a bounded
cross-state staging planner while preserving portfolio, security, epoch, valuation-date, and
correlation lineage.

## Changes

- Added `VALUATION_SCHEDULER_BACKFILL_UPSERT_CHUNK_SIZE`.
- Added a scheduler backfill chunk planner that aggregates generated valuation jobs across states.
- Replaced per-state `upsert_jobs(...)` calls with bounded chunk upserts.
- Kept missing-history normalization, reprocessing defer logging, gap metrics, and correlation-id
  construction on the existing scheduler path.
- Updated repo context and the operations runbook.

## Expected Improvement

- Reduces avoidable database round trips during large valuation backfills.
- Makes backfill staging throughput depend on a bounded write capacity rather than instrument count.
- Keeps repository idempotency and stale-epoch filtering centralized in `ValuationJobRepository`.
- Preserves existing downstream valuation job payload, key, header, and lifecycle contracts.

## Tests Added

- Runtime settings expose the backfill upsert chunk size.
- Scheduler reads the new chunk-size environment variable.
- Multi-state backfill jobs are staged across bounded chunks.
- Chunk-boundary tests preserve state-specific valuation dates and correlation lineage.

Existing `ValuationJobRepository.upsert_jobs(...)` integration coverage continues to prove duplicate
normalization, stale-epoch filtering, and idempotent database upsert behavior.

## Validation Evidence

```powershell
python -m pytest tests\unit\libs\portfolio-common\test_valuation_runtime_settings.py tests\unit\services\valuation_orchestrator_service\core\test_valuation_scheduler.py -q
python -m ruff check src\libs\portfolio-common\portfolio_common\valuation_runtime_settings.py src\services\valuation_orchestrator_service\app\core\valuation_scheduler.py tests\unit\libs\portfolio-common\test_valuation_runtime_settings.py tests\unit\services\valuation_orchestrator_service\core\test_valuation_scheduler.py
python -m ruff format --check src\libs\portfolio-common\portfolio_common\valuation_runtime_settings.py src\services\valuation_orchestrator_service\app\core\valuation_scheduler.py tests\unit\libs\portfolio-common\test_valuation_runtime_settings.py tests\unit\services\valuation_orchestrator_service\core\test_valuation_scheduler.py
```

Final docs, architecture, and diff checks are recorded in the issue comment before commit.

## Downstream Compatibility Impact

No API route, DTO, OpenAPI schema, database schema, Kafka topic, event payload, Kafka key/header,
consumer group, or runtime topology changed.

Intentional behavior change: backfill job staging writes generated jobs in bounded chunks across
states instead of writing once per state. Job identity, correlation lineage, duplicate idempotency,
and stale-epoch filtering remain owned by the existing repository contract.

## Same-Pattern Scan

`rg` found no remaining scheduler per-state `upsert_jobs(...)` loop after this change. Remaining
`upsert_jobs(...)` call sites are the single-job compatibility method and repository/integration
tests. Broader bulk-write chunking for unrelated repositories remains separate issue scope.

## Docs, Context, And Skill Decision

- Repo context updated with the backfill chunking rule.
- Operations runbook updated with the chunk-size setting.
- No wiki source update is required because no separate operator workflow page changed.
- No platform skill update is required in this slice; the durable lesson is repo-specific and now
  covered by repo context plus this review entry.

## Remaining Hotspots

The scheduler still generates one in-memory `ValuationJobUpsert` per valuation date before chunked
upsert. If future production evidence shows very long date gaps exhausting memory before chunking,
move the date-range generation itself to a streaming chunk builder without changing repository
idempotency semantics.
