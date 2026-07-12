# CR-884 Reference Coverage Calculations Boundary

Date: 2026-06-04

## Scope

Reduce maintainability and method-complexity debt in query-service reference-data coverage
reporting without changing benchmark, risk-free, price, or return repository contracts.

## Finding

`src/services/query_service/app/repositories/reference_data_repository.py` remains a C-ranked
maintainability hotspot because it owns a broad query repository surface. Within that module,
`get_benchmark_coverage` mixed repository reads with benchmark component activation, index-price
date indexing, benchmark-return date intersection, quality-status aggregation, and evidence
timestamp selection.

That made the reference-data repository harder to review because calculation policy and database
read orchestration lived in the same method.

## Action

Extracted pure reference coverage helpers into
`src/services/query_service/app/repositories/reference_coverage_calculations.py`, including:

1. latest reference evidence timestamp selection,
2. quality-status count aggregation,
3. benchmark coverage observed-date derivation,
4. price-point index lookup by series date,
5. active benchmark component index selection for a date window.

Updated `ReferenceDataRepository.get_benchmark_coverage` and
`ReferenceDataRepository.get_risk_free_coverage` to delegate calculation policy to those helpers
while preserving their public response shape.

## Result

`get_benchmark_coverage` now reports `A (4)` under Radon cyclomatic complexity instead of `C (11)`.
`reference_data_repository.py` improved from `C (4.26)` to `C (6.94)` under Radon
maintainability, and the extracted helper module reports `A (50.34)`.

This is a real bounded improvement, but not final closure: `reference_data_repository.py` remains a
C-ranked maintainability hotspot and the current C-hotspot count remains 8.

## Evidence

- `python -m pytest tests\unit\services\query_service\repositories\test_reference_data_repository.py -q`
  => `32 passed`
- `python -m radon cc src\services\query_service\app\repositories\reference_data_repository.py src\services\query_service\app\repositories\reference_coverage_calculations.py -s`
  => `get_benchmark_coverage - A (4)` and all extracted helper functions A-ranked
- `python -m radon mi src\services\query_service\app\repositories\reference_data_repository.py src\services\query_service\app\repositories\reference_coverage_calculations.py -s`
  => `reference_data_repository.py - C (6.94)` and
  `reference_coverage_calculations.py - A (50.34)`
- `make quality-maintainability-gate` => clean
- `make quality-complexity-gate` => clean
- `make typecheck` => clean
- `make quality-bandit-gate` => clean
- `make quality-vulture-source-gate` => clean
- `make quality-deptry-source-gate` => clean

## Wiki Decision

No wiki source update is required for this slice. The change is an internal query-service
repository maintainability refactor with repository-local architecture and quality evidence; it
does not change operator-facing runtime behavior, API surface, onboarding flow, or wiki-owned
product truth.
