# CR-1151 Reconciliation Transaction Cashflow Workflow

Date: 2026-06-22

## Scope

Transaction-to-cashflow reconciliation run orchestration in
`src/services/financial_reconciliation_service/app/services/reconciliation_service.py`.

## Finding

`ReconciliationService.run_transaction_cashflow(...)` mixed run creation, idempotent duplicate-run
return, row loading, row examination counting, missing-cashflow finding construction, rule-mismatch
field comparison, mismatch finding construction, finding persistence, run summary, run completion,
metric observation, and response return in one C-ranked service method.

Radon reported:

- `run_transaction_cashflow`: `C (11)`

## Action Taken

Extracted focused helpers for:

- per-row transaction cashflow finding construction,
- missing-cashflow finding construction,
- cashflow rule mismatch comparison,
- rule-mismatch finding construction.

The run creation semantics, duplicate-run behavior, examined count, finding types, expected/observed
payloads, detail payloads, summary behavior, and metric observation remain unchanged.

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
- Result: `run_transaction_cashflow` is `A (2)`

Measured movement:

- `run_transaction_cashflow`: `C (11)` -> `A (2)`

## Residual Risk

This slice does not change reconciliation repository queries, cashflow rule semantics, finding
storage, automatic bundle behavior, or timeseries integrity reconciliation. The larger
`run_timeseries_integrity(...)` method remains a separate measured hotspot.

## Bank-Buyable Control Movement

This slice improves:

- reviewability of transaction-to-cashflow control logic,
- isolation of expected/observed mismatch payload construction,
- direct proof across the reconciliation service behavior suite.

It does not claim full bank-buyable readiness for `lotus-core`.
