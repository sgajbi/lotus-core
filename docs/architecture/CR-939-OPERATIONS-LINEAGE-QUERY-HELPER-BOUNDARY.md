# CR-939: Operations Lineage Query Helper Boundary

Date: 2026-06-04

## Scope

Move operations lineage SQL helper construction out of `OperationsRepository` without changing
support endpoint contracts, lineage-key filtering, artifact-gap prioritization, database execution,
or database schema.

## Finding

`OperationsRepository` still owned lineage SQL helper policy inline, including latest artifact-date
subqueries, artifact-gap classification, lineage priority ordering, and lineage-key select shaping.
Those helpers are pure query construction; the repository only needs to normalize request filters,
compose the portfolio-scoped statement, execute it, and return rows.

## Action

Extracted `operations_lineage_queries.py` with helpers for:

- latest artifact-date correlated subqueries,
- lineage artifact-gap classification,
- lineage priority ordering,
- lineage-key select construction.

`OperationsRepository` now delegates lineage query policy to the helper while preserving portfolio
scope, request filters, pagination, ordering, and support response shape.

## Result

`operations_repository.py` shrank from 2,456 SLOC to 2,388 SLOC and remains `C (0.00)` under Radon
maintainability because the active repository is still large. The new
`operations_lineage_queries.py` module reports `A (58.81)` under Radon maintainability, with no
B-or-worse complexity findings in the scoped repository/helper check output. Additional operations
repository helper extractions are still required to remove this active C-ranked hotspot.

## Evidence

- `python -m pytest tests\unit\services\query_service\repositories\test_operations_repository.py -q`
  => 67 passed
- `python -m ruff check src\services\query_service\app\repositories\operations_repository.py src\services\query_service\app\repositories\operations_health_queries.py src\services\query_service\app\repositories\operations_missing_fx_queries.py src\services\query_service\app\repositories\operations_lineage_queries.py tests\unit\services\query_service\repositories\test_operations_repository.py`
  => all checks passed
- `python -m ruff format --check src\services\query_service\app\repositories\operations_repository.py src\services\query_service\app\repositories\operations_health_queries.py src\services\query_service\app\repositories\operations_missing_fx_queries.py src\services\query_service\app\repositories\operations_lineage_queries.py tests\unit\services\query_service\repositories\test_operations_repository.py`
  => 5 files already formatted
- `python -m radon raw src\services\query_service\app\repositories\operations_repository.py src\services\query_service\app\repositories\operations_lineage_queries.py`
  => `operations_repository.py` 2,388 SLOC; `operations_lineage_queries.py` 72 SLOC
- `python -m radon mi src\services\query_service\app\repositories\operations_repository.py src\services\query_service\app\repositories\operations_lineage_queries.py -s`
  => repository `C (0.00)`, helper `A (58.81)`
- `python -m radon cc src\services\query_service\app\repositories\operations_repository.py src\services\query_service\app\repositories\operations_lineage_queries.py -s`
  => no B-or-worse complexity findings in the scoped repository/helper check output
- `make quality-complexity-gate`
  => passed
- `make quality-maintainability-gate`
  => passed

## Wiki Decision

No wiki source update is required. This is an internal operations repository lineage-query helper
extraction that preserves API contracts, SQL semantics, operator workflows, and public
documentation truth.
