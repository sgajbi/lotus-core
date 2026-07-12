# CR-944: Operations Reconciliation Run Scope Helper Boundary

Date: 2026-06-04

## Scope

Move financial reconciliation run scope and priority construction out of `OperationsRepository`
without changing support endpoint contracts, run filtering, as-of handling, started-at as-of
handling, priority ordering, database execution, or database schema.

## Finding

`OperationsRepository` still owned reconciliation-run status normalization, failed/replay priority
ordering, time filtering, identity filtering, attribute filtering, and composed run-scope helpers
inline. Those helpers are pure support-query policy; the repository only needs to compose
endpoint-specific statements, execute them, and return rows or DTOs.

## Action

Extracted `operations_reconciliation_run_queries.py` with helpers for:

- reconciliation-run status normalization,
- reconciliation-run failed/replay priority ordering,
- as-of and started-at-as-of filtering,
- run identity filtering,
- reconciliation type, business-date, and epoch filtering,
- composed reconciliation-run scope construction.

`OperationsRepository` now delegates reconciliation-run filtering and priority policy to the helper
while preserving database execution, pagination, latest-run ordering, and response shape.

## Result

`operations_repository.py` shrank from 1,689 SLOC to 1,596 SLOC and remains `C (0.00)` under Radon
maintainability because the active repository is still large. The new
`operations_reconciliation_run_queries.py` module reports `A (47.04)` under Radon maintainability,
with no B-or-worse complexity findings in the scoped repository/helper check output. Additional
operations repository extractions are still required to remove this active C-ranked hotspot.

## Evidence

- `python -m pytest tests\unit\services\query_service\repositories\test_operations_repository.py -q`
  => 67 passed
- `python -m ruff check src\services\query_service\app\repositories\operations_repository.py src\services\query_service\app\repositories\operations_reconciliation_run_queries.py tests\unit\services\query_service\repositories\test_operations_repository.py`
  => all checks passed
- `python -m ruff format --check src\services\query_service\app\repositories\operations_repository.py src\services\query_service\app\repositories\operations_reconciliation_run_queries.py tests\unit\services\query_service\repositories\test_operations_repository.py`
  => 3 files already formatted
- `python -m radon raw src\services\query_service\app\repositories\operations_repository.py src\services\query_service\app\repositories\operations_reconciliation_run_queries.py`
  => `operations_repository.py` 1,596 SLOC; `operations_reconciliation_run_queries.py` 93 SLOC
- `python -m radon mi src\services\query_service\app\repositories\operations_repository.py src\services\query_service\app\repositories\operations_reconciliation_run_queries.py -s`
  => repository `C (0.00)`, helper `A (47.04)`
- `python -m radon cc src\services\query_service\app\repositories\operations_repository.py src\services\query_service\app\repositories\operations_reconciliation_run_queries.py -s`
  => no B-or-worse complexity findings in the scoped repository/helper check output
- `make quality-complexity-gate`
  => passed
- `make quality-maintainability-gate`
  => passed

## Wiki Decision

No wiki source update is required. This is an internal operations repository reconciliation-run
query-scope helper extraction that preserves API contracts, SQL semantics, operator workflows, and
public documentation truth.
