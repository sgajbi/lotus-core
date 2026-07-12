# CR-232 Timeseries Integrity DB Proof Review

## Scope

Extend timeseries-integrity reconciliation proof from mocked service inputs to DB-backed route and
repository execution.

## Finding

The reconciliation app already had DB-backed proof for one `timeseries_integrity` failure mode:

1. snapshot-count completeness gap,
2. portfolio-vs-position aggregate mismatch.

But it still did not prove the asymmetric case where position-timeseries evidence exists for a
portfolio-day-epoch and the corresponding `portfolio_timeseries` row is missing entirely.

That is a meaningful control case. In production, partial aggregation or interrupted fan-in can
manifest as “position rows exist, portfolio row absent,” and the reconciliation surface must flag
that condition directly against persisted rows.

## Actions Taken

Added a DB-backed integration test that seeds:

1. one portfolio,
2. one snapshot row,
3. one position-timeseries row,
4. no portfolio-timeseries row,

then exercises `POST /reconciliation/runs/timeseries-integrity` and verifies:

1. one finding is persisted,
2. the finding type is `missing_portfolio_timeseries`,
3. the detail records the expected `position_timeseries_rows` count,
4. the reconciliation summary is failed.

## Why This Matters

This strengthens the banking-grade control posture in two ways:

1. the control is now proven against real persisted rows, not just mocked service inputs,
2. one of the most operationally important partial-aggregation failure modes is now locked down by
   an integration test at the API boundary.

## Evidence

- `tests/integration/services/financial_reconciliation_service/test_financial_reconciliation_app.py`
- `pytest tests/integration/services/financial_reconciliation_service/test_financial_reconciliation_app.py -q`
