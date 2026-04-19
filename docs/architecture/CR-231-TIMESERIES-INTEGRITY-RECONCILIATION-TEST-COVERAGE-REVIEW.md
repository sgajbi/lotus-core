# CR-231 Timeseries Integrity Reconciliation Test Coverage Review

## Scope

Review lower-level test coverage for the `timeseries_integrity` financial reconciliation path.

## Finding

`ReconciliationService.run_timeseries_integrity(...)` already encoded meaningful portfolio-day
invariants:

1. missing `portfolio_timeseries` when position aggregates exist,
2. missing `position_timeseries` when portfolio rows exist,
3. completeness gap between snapshot count and position-timeseries count,
4. arithmetic mismatch between portfolio-level figures and the aggregated position-level figures.

But those invariants were materially under-tested. The unit suite covered transaction cashflow,
position valuation, and automatic bundle orchestration, while the timeseries arithmetic path had no
direct characterization of its error conditions.

That left a real banking-grade gap: a drift in portfolio-day totals could survive until heavier
runtime or downstream investigation instead of failing at the service layer.

## Actions Taken

Added direct unit coverage for:

1. `missing_portfolio_timeseries` when aggregate rows exist without a portfolio row,
2. combined `position_timeseries_completeness_gap` and
   `portfolio_timeseries_aggregate_mismatch` when snapshot counts and portfolio-vs-aggregate figures
   diverge.

The new tests assert the actual finding types, deltas, and summary status so the service contract is
proven below integration/E2E level.

## Why This Matters

This does not change production behavior. It makes a critical cross-table figure-consistency contract
harder to regress silently:

1. portfolio-day arithmetic drift now fails closer to the source,
2. completeness and aggregate-mismatch semantics are explicitly documented by tests,
3. downstream consumers get stronger assurance that reconciliation evidence reflects the intended
   control logic.

## Evidence

- `tests/unit/services/financial_reconciliation_service/test_reconciliation_service.py`
- `pytest tests/unit/services/financial_reconciliation_service/test_reconciliation_service.py -q`
