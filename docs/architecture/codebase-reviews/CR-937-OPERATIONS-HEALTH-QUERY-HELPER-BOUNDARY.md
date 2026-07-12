# CR-937: Operations Health Query Helper Boundary

Date: 2026-06-04

## Scope

Move reusable operations health aggregation and row-shaping helpers out of
`OperationsRepository` without changing support endpoint contracts, SQL predicates, health
classification semantics, database execution, metrics, or database schema.

## Finding

`OperationsRepository` still owned support-job and analytics-export health aggregation helpers
inline. Those helpers build reusable aggregate subqueries, oldest-open-job selectors, health
thresholds, and DTO row mappers. They do not need repository instance state; the repository only
needs to build portfolio-scoped base statements, execute the final statement, and return the health
summary.

## Action

Extracted `operations_health_queries.py` with helpers for:

- integer and latency row-value normalization,
- support-job health thresholds,
- support-job aggregate and oldest-open selectors,
- support-job health result projection and DTO shaping,
- analytics-export health aggregate and oldest-open selectors,
- analytics-export health result projection and DTO shaping.

`OperationsRepository` now delegates health aggregation policy to the helper while preserving
portfolio-scoped base queries, database execution, support endpoint response models, and SQL shape.

## Result

`operations_repository.py` shrank from 2,684 SLOC to 2,522 SLOC and remains `C (0.00)` under Radon
maintainability because the active repository is still very large. The new
`operations_health_queries.py` module reports `A (49.26)` under Radon maintainability, with no
B-or-worse complexity findings in the scoped repository/helper check output. Additional operations
repository helper extractions are still required to remove this active C-ranked hotspot.

## Evidence

- `python -m pytest tests\unit\services\query_service\repositories\test_operations_repository.py -q`
  => 67 passed
- `python -m ruff check src\services\query_service\app\repositories\operations_repository.py src\services\query_service\app\repositories\operations_health_queries.py tests\unit\services\query_service\repositories\test_operations_repository.py`
  => all checks passed
- `python -m ruff format --check src\services\query_service\app\repositories\operations_repository.py src\services\query_service\app\repositories\operations_health_queries.py tests\unit\services\query_service\repositories\test_operations_repository.py`
  => 3 files already formatted
- `python -m radon raw src\services\query_service\app\repositories\operations_repository.py src\services\query_service\app\repositories\operations_health_queries.py`
  => `operations_repository.py` 2,522 SLOC; `operations_health_queries.py` 168 SLOC
- `python -m radon mi src\services\query_service\app\repositories\operations_repository.py src\services\query_service\app\repositories\operations_health_queries.py -s`
  => repository `C (0.00)`, helper `A (49.26)`
- `python -m radon cc src\services\query_service\app\repositories\operations_repository.py src\services\query_service\app\repositories\operations_health_queries.py -s`
  => no B-or-worse complexity findings in the scoped repository/helper check output
- `make quality-complexity-gate`
  => passed
- `make quality-maintainability-gate`
  => passed

## Wiki Decision

No wiki source update is required. This is an internal operations repository health-query helper
extraction that preserves API contracts, SQL semantics, operator workflows, and public
documentation truth.
