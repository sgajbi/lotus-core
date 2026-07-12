# CR-885 Load-Run Progress Repository Boundary

Date: 2026-06-04

## Scope

Reduce monolithic query construction and result-mapping complexity in query-service load-run
progress reporting without changing the operations API response contract or repository SQL scope.

## Finding

`OperationsRepository.get_load_run_progress` was a D-ranked method at `D (27)`. It mixed run-id
pattern construction, ingestion count statements, artifact count statements, valuation and
aggregation job summaries, valuation-to-position-timeseries handoff latency SQL, latest artifact
timestamps, database execution, null normalization, optional latency conversion, and
`LoadRunProgressSummary` response assembly in one method.

That shape made an operations-readiness endpoint harder to review, and it increased the risk that
future diagnostics, latency, or lineage additions would be added directly to the orchestration
method.

## Action

Split the load-run progress repository path into named helpers:

1. `_load_run_progress_scalar_statements(...)` for scalar count and latest-artifact statements,
2. `_load_run_progress_execute_statements(...)` for summary-row statements,
3. `_load_run_progress_valuation_handoff_statements(...)` for valuation-to-position-timeseries
   handoff latency and missing-handoff SQL,
4. `_load_run_progress_summary_from_rows(...)` for `LoadRunProgressSummary` assembly,
5. `_int_or_zero(...)` and `_float_or_none(...)` for repeated result normalization.

The public `get_load_run_progress(...) -> LoadRunProgressSummary` repository method still owns the
database execution boundary and preserves the same response model.

## Result

`get_load_run_progress` now reports `A (3)` under Radon cyclomatic complexity instead of `D (27)`.
The extracted load-run helper methods all report A-ranked complexity.

This is a real operations-boundary improvement, but not final closure:
`operations_repository.py` remains `C (0.00)` under Radon maintainability because the repository
module is still very large, and the current C-ranked maintainability hotspot count remains 8.

## Evidence

- `python -m pytest tests\unit\services\query_service\repositories\test_operations_repository.py -q`
  => `67 passed`
- `python -m pytest tests\integration\services\query_service\test_int_operations_service.py -q -k "load_run_progress"`
  => `2 passed, 16 deselected`
- `python -m radon cc src\services\query_service\app\repositories\operations_repository.py -s`
  => `get_load_run_progress - A (3)` and load-run helper methods A-ranked
- `python -m radon mi src\services\query_service\app\repositories\operations_repository.py -s`
  => `operations_repository.py - C (0.00)`
- `make quality-ruff-gate` => clean
- `make quality-ruff-format-gate` => clean
- `make quality-maintainability-gate` => clean
- `make quality-complexity-gate` => clean
- `make typecheck` => clean
- `make quality-bandit-gate` => clean
- `make quality-vulture-source-gate` => clean
- `make quality-deptry-source-gate` => clean

## Wiki Decision

No wiki source update is required for this slice. The change is an internal query-service
repository refactor with repository-local architecture and quality evidence; it does not change
operator-facing runtime behavior, API surface, onboarding flow, or wiki-owned product truth.
