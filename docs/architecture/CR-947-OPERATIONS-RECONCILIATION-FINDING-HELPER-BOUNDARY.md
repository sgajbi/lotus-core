# CR-947: Operations Reconciliation Finding Helper Boundary

Date: 2026-06-05

## Scope

Move reconciliation-finding scope construction, severity ordering, and summary aggregation out of
`OperationsRepository` without changing support endpoint contracts, filter semantics, as-of
visibility, security-id normalization, blocking-finding selection, database execution, pagination,
or database schema.

## Finding

`OperationsRepository` still owned reconciliation-finding scope filtering, severity-priority
ordering, summary base selection, aggregate counts, top-blocking finding selection, and
`ReconciliationFindingSummary` row shaping inline. Those helpers are reusable support-query policy
and DTO shaping. The repository only needs to normalize request filters, execute statements, and
return rows or DTOs.

## Action

Extracted `operations_reconciliation_finding_queries.py` with helpers for:

- reconciliation-finding run, as-of, finding-id, security-id, and transaction-id filtering,
- severity-priority ordering,
- summary base select construction,
- aggregate and top-blocking summary select construction,
- `ReconciliationFindingSummary` row shaping.

`OperationsRepository` now delegates reconciliation-finding query policy and summary shaping to the
helper while preserving database execution, ordering, pagination, and response shape.

## Result

`operations_repository.py` shrank from 1,403 SLOC to 1,332 SLOC and improved from `C (4.42)` to
`C (6.24)` under Radon maintainability, but remains a C-ranked active hotspot. The new
`operations_reconciliation_finding_queries.py` module reports `A (50.89)` under Radon
maintainability, with no B-or-worse complexity findings in the scoped repository/helper check
output. Additional operations repository extractions are still required to remove this active
C-ranked hotspot.

## Evidence

- `python -m pytest tests\unit\services\query_service\repositories\test_operations_repository.py -q`
  => 67 passed
- `python -m ruff check src\services\query_service\app\repositories\operations_repository.py src\services\query_service\app\repositories\operations_reconciliation_finding_queries.py tests\unit\services\query_service\repositories\test_operations_repository.py`
  => all checks passed
- `python -m ruff format --check src\services\query_service\app\repositories\operations_repository.py src\services\query_service\app\repositories\operations_reconciliation_finding_queries.py tests\unit\services\query_service\repositories\test_operations_repository.py`
  => 3 files already formatted
- `python -m radon raw src\services\query_service\app\repositories\operations_repository.py src\services\query_service\app\repositories\operations_reconciliation_finding_queries.py`
  => `operations_repository.py` 1,332 SLOC; `operations_reconciliation_finding_queries.py` 88 SLOC
- `python -m radon mi src\services\query_service\app\repositories\operations_repository.py src\services\query_service\app\repositories\operations_reconciliation_finding_queries.py -s`
  => repository `C (6.24)`, helper `A (50.89)`
- `python -m radon cc src\services\query_service\app\repositories\operations_repository.py src\services\query_service\app\repositories\operations_reconciliation_finding_queries.py -s`
  => no B-or-worse complexity findings in the scoped repository/helper check output
- `make quality-complexity-gate`
  => passed
- `make quality-maintainability-gate`
  => passed

## Wiki Decision

No wiki source update is required. This is an internal operations repository reconciliation-finding
query-helper extraction that preserves API contracts, SQL semantics, operator workflows, and public
documentation truth.
