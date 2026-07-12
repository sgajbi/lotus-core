# CR-097 Watermark Advance Mismatch Visibility Review

## Scope

- valuation scheduler watermark advancement
- visibility of epoch-fenced stale-update drops

## Finding

`PositionStateRepository.bulk_update_states(...)` is now epoch-fenced, which prevents stale
writers from overwriting newer canonical state. That solved the correctness problem, but the
valuation scheduler still treated partial advancement as routine success.

If the scheduler prepared `N` updates and only `M < N` were actually written because some
rows had already advanced to a newer epoch, the system remained correct but the stale-epoch
skips were invisible in normal logs.

## Action Taken

- Updated `ValuationScheduler._advance_watermarks(...)` to distinguish:
  - full advancement
  - partial advancement due to stale skips
- When `updated_count != prepared_count`, the scheduler now emits a warning with:
  - prepared count
  - updated count
  - stale skipped count
  - sample keys/dates
- Added unit coverage for the partial-update warning path

## Result

Epoch-fenced drops are now operationally visible instead of silently blended into normal
advancement logs. This improves diagnosis of replay races and scheduler concurrency without
changing the underlying state model.

## Evidence

- `src/services/valuation_orchestrator_service/app/core/valuation_scheduler.py`
- `tests/unit/services/valuation_orchestrator_service/core/test_valuation_scheduler.py`
