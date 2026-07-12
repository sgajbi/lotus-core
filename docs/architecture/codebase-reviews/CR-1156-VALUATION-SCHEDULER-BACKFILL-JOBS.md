# CR-1156 Valuation Scheduler Backfill Jobs

Date: 2026-06-22

## Scope

- `src/services/valuation_orchestrator_service/app/core/valuation_scheduler.py`

## Finding

`ValuationScheduler._create_backfill_jobs(...)` mixed latest business-date lookup, backfill state
loading, first-open date lookup, no-history state partitioning, no-history normalization,
reprocessing defer logging, lag metrics, missing-history logging, deterministic backfill job request
construction, durable job upsert, created-job metrics, and staged-job logging in one C-ranked
method.

This made it difficult to inspect the exact boundary between supportable current-epoch history,
no-history normalization, and deterministic job staging.

## Action

Extracted focused helpers for:

- no-history state partitioning,
- no-history normalization update construction,
- no-history normalization persistence and logging,
- reprocessing defer logging,
- backfill gap metric observation,
- missing current-epoch history logging,
- deterministic `ValuationJobUpsert` request construction,
- per-state job staging and metric observation,
- ordered per-state backfill processing.

The first-open date behavior, job valuation dates, correlation IDs, no-history normalization
payloads, reprocessing defer posture, lag metrics, and durable upsert behavior are preserved.

## Measured Signal

- Before: `ValuationScheduler._create_backfill_jobs(...)` was `C (20)`.
- After: `ValuationScheduler._create_backfill_jobs(...)` is `A (4)`.
- Source-wide C-or-worse scan is empty:
  - `python -m radon cc src -s --exclude "*/build/*" | Select-String -Pattern " - [C-F] \("`
  - no output

## Validation

- `python -m pytest tests\unit\services\valuation_orchestrator_service\core\test_valuation_scheduler.py -q`
  - `20 passed`
- `python -m ruff check src/services/valuation_orchestrator_service/app/core/valuation_scheduler.py tests/unit/services/valuation_orchestrator_service/core/test_valuation_scheduler.py`
  - passed
- `python -m ruff format src/services/valuation_orchestrator_service/app/core/valuation_scheduler.py`
  - passed
- `python -m radon cc src\services\valuation_orchestrator_service\app\core\valuation_scheduler.py -s --exclude "*/build/*"`
  - `ValuationScheduler._create_backfill_jobs - A (4)`

## Residual Risk

`ValuationScheduler._dispatch_jobs(...)` and `_advance_watermarks(...)` remain B-ranked. They are
not C-ranked blockers, but can be reviewed separately if dispatch confirmation or watermark
normalization evidence becomes the next measured reliability target.

