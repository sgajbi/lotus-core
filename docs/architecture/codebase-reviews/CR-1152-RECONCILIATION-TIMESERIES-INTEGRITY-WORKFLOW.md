# CR-1152 Reconciliation Timeseries Integrity Workflow

Date: 2026-06-22

## Scope

Portfolio timeseries integrity reconciliation in
`src/services/financial_reconciliation_service/app/services/reconciliation_service.py`.

## Finding

`ReconciliationService.run_timeseries_integrity(...)` mixed run creation, duplicate-run return,
portfolio row loading, position aggregate loading, snapshot count loading, scope-key map
construction, authoritative metric aggregation, missing portfolio-row finding construction, missing
position-row finding construction, completeness-gap finding construction, metric pair extraction,
tolerance-based aggregate mismatch detection, mismatch finding construction, run summary,
completion, metric observation, and response return in one C-ranked service method.

Radon reported:

- `run_timeseries_integrity`: `C (19)`

## Action Taken

Extracted focused helpers for:

- timeseries scope map construction,
- deterministic scope-key ordering,
- per-key timeseries integrity finding construction,
- missing portfolio-timeseries findings,
- missing position-timeseries findings,
- completeness-gap findings,
- portfolio/authoritative metric pair extraction,
- tolerance-based metric mismatch detection,
- aggregate mismatch finding construction.

The examined count, finding types, expected/observed payloads, tolerance semantics, authoritative
fallback behavior, summary behavior, and metric observation remain unchanged.

## Evidence

Focused unit proof:

- `python -m pytest tests\unit\services\financial_reconciliation_service\test_reconciliation_service.py -q`
- Result: `13 passed`

Focused static proof:

- `python -m ruff check src/services/financial_reconciliation_service/app/services/reconciliation_service.py tests/unit/services/financial_reconciliation_service/test_reconciliation_service.py`
- Result: passed

Focused format proof:

- `python -m ruff format --check src/services/financial_reconciliation_service/app/services/reconciliation_service.py tests/unit/services/financial_reconciliation_service/test_reconciliation_service.py`
- Result: passed

Focused complexity proof:

- `python -m radon cc src/services/financial_reconciliation_service/app/services/reconciliation_service.py -s --exclude "*/build/*"`
- Result: `run_timeseries_integrity` is `A (3)`

Measured movement:

- `run_timeseries_integrity`: `C (19)` -> `A (3)`
- `reconciliation_service.py`: no C-or-worse functions remain

## Residual Risk

This slice does not change reconciliation repository queries, authoritative metric methodology,
finding persistence, route contracts, or automatic bundle behavior. Remaining C-ranked hotspots are
now concentrated in valuation orchestrator worker/scheduler control loops.

## Bank-Buyable Control Movement

This slice improves:

- reviewability of portfolio timeseries integrity controls,
- isolation of completeness and aggregate mismatch finding construction,
- direct proof across the reconciliation service behavior suite.

It does not claim full bank-buyable readiness for `lotus-core`.
