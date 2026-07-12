# CR-098 Terminal Reprocessing Normalization Review

## Scope

- valuation scheduler terminal-state normalization
- `PositionState.status` semantics at latest business date

## Finding

The valuation scheduler only queried lagging keys via
`watermark_date < latest_business_date`. That meant a key could remain at:

- `status = "REPROCESSING"`
- `watermark_date = latest_business_date`

without ever being normalized back to `CURRENT`.

The data plane was effectively complete, but the canonical control row still reported an
active reprocessing state. That is semantically stale and also made the reprocessing
gauge undercount active/stale states.

## Action Taken

- Added `ValuationRepositoryBase.get_terminal_reprocessing_states(...)`
- Updated `ValuationScheduler._advance_watermarks(...)` to:
  - include terminal `REPROCESSING` rows in the active reprocessing gauge
  - normalize them back to `CURRENT` via epoch-fenced `bulk_update_states(...)`
- Added unit coverage proving:
  - terminal `REPROCESSING` rows are normalized
  - the normal lagging-state path still behaves correctly

## Result

`PositionState.status` is now brought back into alignment once a key has fully caught up to
the latest business date. This removes a stale-state survivability gap in the scheduler
state machine.

## Evidence

- `src/libs/portfolio-common/portfolio_common/valuation_repository_base.py`
- `src/services/valuation_orchestrator_service/app/core/valuation_scheduler.py`
- `tests/unit/services/valuation_orchestrator_service/core/test_valuation_scheduler.py`
