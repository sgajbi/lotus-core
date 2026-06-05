# CR-945: Operations Portfolio Control Scope Helper Boundary

Date: 2026-06-04

## Scope

Move portfolio-control stage scope and priority construction out of `OperationsRepository` without
changing support endpoint contracts, stage filtering, portfolio-stage transaction scoping, priority
ordering, database execution, pagination, or database schema.

## Finding

`OperationsRepository` still owned portfolio-control stage status normalization, failed/replay
priority ordering, identity filtering, business-date filtering, and composed stage-scope helpers
inline. Those helpers are pure support-query policy; the repository only needs to compose
endpoint-specific statements, execute them, and return rows.

## Action

Extracted `operations_portfolio_control_queries.py` with helpers for:

- portfolio-control status normalization,
- failed/replay priority ordering,
- stage identity filtering,
- business-date filtering,
- composed portfolio-control stage scope construction.

`OperationsRepository` now delegates portfolio-control stage filtering and priority policy to the
helper while preserving database execution, ordering, pagination, and response shape.

## Result

`operations_repository.py` shrank from 1,596 SLOC to 1,538 SLOC and improved from `C (0.00)` to
`C (0.21)` under Radon maintainability, but remains a C-ranked active hotspot. The new
`operations_portfolio_control_queries.py` module reports `A (53.89)` under Radon maintainability,
with no B-or-worse complexity findings in the scoped repository/helper check output. Additional
operations repository extractions are still required to remove this active C-ranked hotspot.

## Evidence

- `python -m pytest tests\unit\services\query_service\repositories\test_operations_repository.py -q`
  => 67 passed
- `python -m ruff check src\services\query_service\app\repositories\operations_repository.py src\services\query_service\app\repositories\operations_portfolio_control_queries.py tests\unit\services\query_service\repositories\test_operations_repository.py`
  => all checks passed
- `python -m ruff format --check src\services\query_service\app\repositories\operations_repository.py src\services\query_service\app\repositories\operations_portfolio_control_queries.py tests\unit\services\query_service\repositories\test_operations_repository.py`
  => 3 files already formatted
- `python -m radon raw src\services\query_service\app\repositories\operations_repository.py src\services\query_service\app\repositories\operations_portfolio_control_queries.py`
  => `operations_repository.py` 1,538 SLOC; `operations_portfolio_control_queries.py` 59 SLOC
- `python -m radon mi src\services\query_service\app\repositories\operations_repository.py src\services\query_service\app\repositories\operations_portfolio_control_queries.py -s`
  => repository `C (0.21)`, helper `A (53.89)`
- `python -m radon cc src\services\query_service\app\repositories\operations_repository.py src\services\query_service\app\repositories\operations_portfolio_control_queries.py -s`
  => no B-or-worse complexity findings in the scoped repository/helper check output
- `make quality-complexity-gate`
  => passed
- `make quality-maintainability-gate`
  => passed

## Wiki Decision

No wiki source update is required. This is an internal operations repository portfolio-control
query-scope helper extraction that preserves API contracts, SQL semantics, operator workflows, and
public documentation truth.
