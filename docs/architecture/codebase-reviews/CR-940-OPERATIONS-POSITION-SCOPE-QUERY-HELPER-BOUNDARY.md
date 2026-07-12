# CR-940: Operations Position Scope Query Helper Boundary

Date: 2026-06-04

## Scope

Move reusable operations position-scope SQL helper construction out of `OperationsRepository`
without changing support endpoint contracts, load-run progress semantics, current snapshot coverage
queries, snapshot valuation coverage queries, database execution, or database schema.

## Finding

`OperationsRepository` still owned reusable SQL scope builders inline for load-run artifact and job
filtering, portfolio/security/epoch evidence filtering, current position-history selection, current
epoch snapshot selection, and latest transaction-date selection. Those helpers are pure query
construction; the repository only needs to normalize request filters, compose endpoint-specific
statements, execute them, and shape support DTO responses.

## Action

Extracted `operations_position_scope_queries.py` with helpers for:

- load-run artifact scope filtering,
- load-run job scope filtering,
- portfolio/security/epoch evidence scope filtering,
- current position-history scope construction,
- current epoch snapshot scope construction,
- latest transaction-date statement construction.

`OperationsRepository` now delegates these reusable scope builders to the helper while preserving
request filters, SQL predicates, ordering, pagination, database execution, and support response
shape.

## Result

`operations_repository.py` shrank from 2,388 SLOC to 2,211 SLOC and remains `C (0.00)` under Radon
maintainability because the active repository is still large. The new
`operations_position_scope_queries.py` module reports `A (38.78)` under Radon maintainability, with
no B-or-worse complexity findings in the scoped repository/helper check output. Additional
operations repository extractions are still required to remove this active C-ranked hotspot.

## Evidence

- `python -m pytest tests\unit\services\query_service\repositories\test_operations_repository.py -q`
  => 67 passed
- `python -m ruff check src\services\query_service\app\repositories\operations_repository.py src\services\query_service\app\repositories\operations_position_scope_queries.py tests\unit\services\query_service\repositories\test_operations_repository.py`
  => all checks passed
- `python -m ruff format --check src\services\query_service\app\repositories\operations_repository.py src\services\query_service\app\repositories\operations_position_scope_queries.py tests\unit\services\query_service\repositories\test_operations_repository.py`
  => 3 files already formatted
- `python -m radon raw src\services\query_service\app\repositories\operations_repository.py src\services\query_service\app\repositories\operations_position_scope_queries.py`
  => `operations_repository.py` 2,211 SLOC; `operations_position_scope_queries.py` 187 SLOC
- `python -m radon mi src\services\query_service\app\repositories\operations_repository.py src\services\query_service\app\repositories\operations_position_scope_queries.py -s`
  => repository `C (0.00)`, helper `A (38.78)`
- `python -m radon cc src\services\query_service\app\repositories\operations_repository.py src\services\query_service\app\repositories\operations_position_scope_queries.py -s`
  => no B-or-worse complexity findings in the scoped repository/helper check output
- `make quality-complexity-gate`
  => passed
- `make quality-maintainability-gate`
  => passed

## Wiki Decision

No wiki source update is required. This is an internal operations repository query-scope helper
extraction that preserves API contracts, SQL semantics, operator workflows, and public
documentation truth.
