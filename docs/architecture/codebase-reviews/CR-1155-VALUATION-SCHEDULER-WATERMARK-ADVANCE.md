# CR-1155 Valuation Scheduler Watermark Advance

Date: 2026-06-22

## Scope

- `src/services/valuation_orchestrator_service/app/core/valuation_scheduler.py`

## Finding

`ValuationScheduler._advance_watermarks(...)` mixed latest business-date lookup, lagging and
terminal state loading, first-open date resolution, active reprocessing metric calculation,
terminal reprocessing normalization, contiguous snapshot lookup, watermark update construction,
epoch-fenced bulk updates, stale-skip observation, and success/warning logging in one C-ranked
method.

This made epoch-fenced update posture and terminal reprocessing normalization harder to verify
independently.

## Action

Extracted focused helpers for:

- terminal reprocessing update construction,
- lagging watermark advance update construction,
- update-example formatting,
- epoch-fenced bulk update execution and stale-skip logging,
- terminal reprocessing normalization,
- lagging watermark advancement.

The persisted bulk update payloads, repository call order, stale-skip metric reasons, and logging
posture are preserved.

## Measured Signal

- Before: `ValuationScheduler._advance_watermarks(...)` was `C (18)`.
- After: `ValuationScheduler._advance_watermarks(...)` is `B (6)`.
- Remaining C-ranked scheduler routine:
  - `ValuationScheduler._create_backfill_jobs(...)`: `C (20)`.

## Validation

- `python -m pytest tests\unit\services\valuation_orchestrator_service\core\test_valuation_scheduler.py -q`
  - `20 passed`
- `python -m ruff check src/services/valuation_orchestrator_service/app/core/valuation_scheduler.py tests/unit/services/valuation_orchestrator_service/core/test_valuation_scheduler.py`
  - passed
- `python -m ruff format src/services/valuation_orchestrator_service/app/core/valuation_scheduler.py`
  - passed
- `python -m radon cc src\services\valuation_orchestrator_service\app\core\valuation_scheduler.py -s --exclude "*/build/*"`
  - `ValuationScheduler._advance_watermarks - B (6)`

## Residual Risk

`_create_backfill_jobs(...)` remains C-ranked and should be reduced separately with scheduler tests
covering first-open date handling, durable job creation, duplicate/stale ownership posture, and
queue metrics.

