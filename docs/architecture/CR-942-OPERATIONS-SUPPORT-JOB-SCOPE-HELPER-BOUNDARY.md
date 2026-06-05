# CR-942: Operations Support Job Scope Helper Boundary

Date: 2026-06-04

## Scope

Move valuation and aggregation support-job scope construction out of `OperationsRepository`
without changing support endpoint contracts, actionable valuation semantics, superseded valuation
filtering, job listing/count filtering, health-summary inputs, database execution, or database
schema.

## Finding

`OperationsRepository` still owned valuation and aggregation job identity filters, business-date
filters, security filters, status filters, and composed job-scope helpers inline. Those helpers are
pure support-query policy; the repository only needs to normalize request filters, supply the
repository-owned actionable valuation SQL expression, execute statements, and return rows or DTOs.

## Action

Extracted `operations_support_job_queries.py` with helpers for:

- support job status normalization,
- valuation job actionable, identity, and attribute scope construction,
- aggregation job identity and attribute scope construction,
- composed valuation and aggregation support-job scope construction.

`OperationsRepository` now delegates valuation and aggregation support-job filtering to the helper
while preserving repository-owned superseded valuation logic, ordering, pagination, database
execution, and response shape.

## Result

`operations_repository.py` shrank from 1,832 SLOC to 1,723 SLOC and remains `C (0.00)` under Radon
maintainability because the active repository is still large. The new
`operations_support_job_queries.py` module reports `A (43.44)` under Radon maintainability, with
no B-or-worse complexity findings in the scoped repository/helper check output. Additional
operations repository extractions are still required to remove this active C-ranked hotspot.

## Evidence

- `python -m pytest tests\unit\services\query_service\repositories\test_operations_repository.py -q`
  => 67 passed
- `python -m ruff check src\services\query_service\app\repositories\operations_repository.py src\services\query_service\app\repositories\operations_support_job_queries.py tests\unit\services\query_service\repositories\test_operations_repository.py`
  => all checks passed
- `python -m ruff format --check src\services\query_service\app\repositories\operations_repository.py src\services\query_service\app\repositories\operations_support_job_queries.py tests\unit\services\query_service\repositories\test_operations_repository.py`
  => 3 files already formatted
- `python -m radon raw src\services\query_service\app\repositories\operations_repository.py src\services\query_service\app\repositories\operations_support_job_queries.py`
  => `operations_repository.py` 1,723 SLOC; `operations_support_job_queries.py` 114 SLOC
- `python -m radon mi src\services\query_service\app\repositories\operations_repository.py src\services\query_service\app\repositories\operations_support_job_queries.py -s`
  => repository `C (0.00)`, helper `A (43.44)`
- `python -m radon cc src\services\query_service\app\repositories\operations_repository.py src\services\query_service\app\repositories\operations_support_job_queries.py -s`
  => no B-or-worse complexity findings in the scoped repository/helper check output
- `make quality-complexity-gate`
  => passed
- `make quality-maintainability-gate`
  => passed

## Wiki Decision

No wiki source update is required. This is an internal operations repository support-job
query-scope helper extraction that preserves API contracts, SQL semantics, operator workflows, and
public documentation truth.
