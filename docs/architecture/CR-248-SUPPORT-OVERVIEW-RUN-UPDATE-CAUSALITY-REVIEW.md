# CR-248 Support Overview Run Update Causality Review

## Scope

- Support overview reconciliation run linkage
- Changing-state causality for mutable run rows

## Finding

After CR-246, the support overview fenced linked reconciliation runs by
`started_at <= latest_control_stage.updated_at`. That prevented later-created runs from leaking into
the overview, but it still allowed a previously started run to carry later status, failure-reason,
or other mutable row updates into the same response through `updated_at`.

## Action Taken

- Tightened `OperationsRepository.get_latest_reconciliation_run_for_portfolio_day(...)`
- Linked reconciliation runs now require both:
  - `started_at <= as_of`
  - `updated_at <= as_of`
- Strengthened repository proof for the stricter causal fence

## Why This Matters

This closes the next mutable-row gap in the support overview. A banking-grade control summary should
not present a reconciliation run state that was written after the control snapshot it is supposed to
explain.

## Evidence

- Files:
  - `src/services/query_service/app/repositories/operations_repository.py`
  - `tests/unit/services/query_service/repositories/test_operations_repository.py`
- Validation:
  - `python -m pytest tests/unit/services/query_service/repositories/test_operations_repository.py tests/unit/services/query_service/services/test_operations_service.py -q`
  - `python -m ruff check src/services/query_service/app/repositories/operations_repository.py tests/unit/services/query_service/repositories/test_operations_repository.py tests/unit/services/query_service/services/test_operations_service.py`

## Follow-up

- Keep applying mutable-row snapshot fences where overview responses pull a durable row that can be
  updated after creation and then expose mutable status or failure fields.
