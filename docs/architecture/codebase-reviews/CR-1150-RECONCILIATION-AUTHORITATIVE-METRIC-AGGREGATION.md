# CR-1150 Reconciliation Authoritative Metric Aggregation

Date: 2026-06-22

## Scope

Authoritative position-timeseries portfolio metric aggregation in
`src/services/financial_reconciliation_service/app/services/reconciliation_service.py`.

## Finding

`ReconciliationService._aggregate_authoritative_portfolio_metrics(...)` mixed authoritative row
loading, metric accumulator initialization, instrument/portfolio currency normalization, FX cache
key construction, latest FX rate lookup, non-positive FX skip behavior, sparse amount zero-defaults,
and portfolio metric accumulation in one C-ranked reconciliation helper.

Radon reported:

- `_aggregate_authoritative_portfolio_metrics`: `C (11)`

## Action Taken

Extracted focused helpers for:

- empty authoritative metric accumulator creation,
- instrument/portfolio currency pair normalization,
- FX conversion requirement detection,
- authoritative metric accumulation,
- cached positive FX-rate resolution.

The row count, non-positive FX skip behavior, sparse amount zero-defaults, FX cache key semantics,
and metric names remain unchanged.

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
- Result: `_aggregate_authoritative_portfolio_metrics` is `A (3)`

Measured movement:

- `_aggregate_authoritative_portfolio_metrics`: `C (11)` -> `A (3)`

## Residual Risk

This slice does not change reconciliation finding semantics, transaction/cashflow reconciliation,
timeseries integrity run orchestration, FX source selection, or repository contracts. The larger
`run_transaction_cashflow(...)` and `run_timeseries_integrity(...)` methods remain separate
measured hotspots.

## Bank-Buyable Control Movement

This slice improves:

- reviewability of authoritative portfolio metric construction,
- isolation of FX conversion supportability behavior,
- direct proof for non-positive FX skip and sparse amount handling.

It does not claim full bank-buyable readiness for `lotus-core`.
