# CR-943: Operations Analytics Export Scope Helper Boundary

Date: 2026-06-04

## Scope

Move analytics-export job scope and priority construction out of `OperationsRepository` without
changing support endpoint contracts, status normalization, listing/count filtering, health-summary
inputs, stale-running ordering, database execution, or database schema.

## Finding

`OperationsRepository` still owned analytics-export status normalization, stale-running priority
ordering, and composed analytics-export job-scope filtering inline. Those helpers are pure support
query policy; the repository only needs to compose endpoint-specific statements, execute them, and
return rows or DTOs.

## Action

Extracted `operations_analytics_export_queries.py` with helpers for:

- analytics-export status normalization,
- analytics-export stale/open job priority ordering,
- analytics-export job scope filtering by portfolio, status, job id, request fingerprint, and
  as-of timestamp.

`OperationsRepository` now delegates analytics-export support-job filtering and ordering policy to
the helper while preserving database execution, pagination, health-summary input shape, and list
response shape.

## Result

`operations_repository.py` shrank from 1,723 SLOC to 1,689 SLOC and remains `C (0.00)` under Radon
maintainability because the active repository is still large. The new
`operations_analytics_export_queries.py` module reports `A (55.97)` under Radon maintainability,
with no B-or-worse complexity findings in the scoped repository/helper check output. Additional
operations repository extractions are still required to remove this active C-ranked hotspot.

## Evidence

- `python -m pytest tests\unit\services\query_service\repositories\test_operations_repository.py -q`
  => 67 passed
- `python -m ruff check src\services\query_service\app\repositories\operations_repository.py src\services\query_service\app\repositories\operations_analytics_export_queries.py tests\unit\services\query_service\repositories\test_operations_repository.py`
  => all checks passed
- `python -m ruff format --check src\services\query_service\app\repositories\operations_repository.py src\services\query_service\app\repositories\operations_analytics_export_queries.py tests\unit\services\query_service\repositories\test_operations_repository.py`
  => 3 files already formatted
- `python -m radon raw src\services\query_service\app\repositories\operations_repository.py src\services\query_service\app\repositories\operations_analytics_export_queries.py`
  => `operations_repository.py` 1,689 SLOC; `operations_analytics_export_queries.py` 37 SLOC
- `python -m radon mi src\services\query_service\app\repositories\operations_repository.py src\services\query_service\app\repositories\operations_analytics_export_queries.py -s`
  => repository `C (0.00)`, helper `A (55.97)`
- `python -m radon cc src\services\query_service\app\repositories\operations_repository.py src\services\query_service\app\repositories\operations_analytics_export_queries.py -s`
  => no B-or-worse complexity findings in the scoped repository/helper check output
- `make quality-complexity-gate`
  => passed
- `make quality-maintainability-gate`
  => passed

## Wiki Decision

No wiki source update is required. This is an internal operations repository analytics-export
query-scope helper extraction that preserves API contracts, SQL semantics, operator workflows, and
public documentation truth.
