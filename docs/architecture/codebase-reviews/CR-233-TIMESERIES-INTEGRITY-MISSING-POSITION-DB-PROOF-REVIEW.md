# CR-233 Timeseries Integrity Missing-Position DB Proof Review

## Scope

Complete the asymmetric timeseries-integrity DB proof by covering the case where
`portfolio_timeseries` exists and `position_timeseries` is missing.

## Finding

After CR-232, the reconciliation app proved the case where position-timeseries rows exist without a
corresponding portfolio-timeseries row. The mirror case was still unproven on the DB-backed route:

1. `portfolio_timeseries` present,
2. no `position_timeseries` rows,
3. snapshot input present.

That is a distinct failure mode. It represents a portfolio-day aggregate being published without its
position-level support, which is exactly the kind of partial or corrupted analytical state that a
banking-grade control needs to flag immediately.

## Actions Taken

Added a DB-backed integration test that seeds:

1. one portfolio,
2. one snapshot row,
3. one `portfolio_timeseries` row,
4. no `position_timeseries` rows,

then executes `POST /reconciliation/runs/timeseries-integrity` and verifies:

1. one finding is persisted,
2. the finding type is `missing_position_timeseries`,
3. the observed value records zero position-timeseries rows,
4. the reconciliation summary is failed.

## Why This Matters

With CR-232 and CR-233 together, both asymmetric missing-row conditions are now proven on the real
route and repository path:

1. position rows without portfolio row,
2. portfolio row without position rows.

That makes the portfolio-day control surface materially tighter against partial aggregation drift.

## Evidence

- `tests/integration/services/financial_reconciliation_service/test_financial_reconciliation_app.py`
- `pytest tests/integration/services/financial_reconciliation_service/test_financial_reconciliation_app.py -q`
