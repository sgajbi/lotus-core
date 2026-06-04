# CR-887 Valuation Job Scope Boundary

Date: 2026-06-04

## Scope

Reduce shared operations repository filtering complexity for portfolio valuation job queries without
changing query semantics, direct job lookup behavior, or operations API response contracts.

## Finding

`OperationsRepository._apply_valuation_job_scope` was a B-ranked method at `B (9)`. It mixed
portfolio scoping, actionable valuation job filtering, as-of visibility, status filtering,
business-date filtering, normalized security filtering, job id filtering, and correlation id
filtering in one helper.

That shape made the valuation operations query path harder to review, especially because direct
job id or correlation id lookups intentionally bypass actionable-job supersession filtering.

## Action

Split valuation job scope construction into named helpers:

1. `_apply_valuation_actionable_scope(...)` for the direct-lookup-aware actionable job rule,
2. `_apply_valuation_attribute_scope(...)` for valuation date and normalized security filters,
3. `_apply_valuation_identity_scope(...)` for job id and correlation id filters.

The public repository query methods still call `_apply_valuation_job_scope(...)`, preserving the
existing repository boundary and generated SQL semantics.

## Result

`_apply_valuation_job_scope` now reports `A (3)` under Radon cyclomatic complexity instead of
`B (9)`. The extracted valuation scope helpers all report A-ranked complexity.

This is a real shared-filter boundary improvement, but not final closure:
`operations_repository.py` remains `C (0.00)` under Radon maintainability because the repository
module is still very large, and the current C-ranked maintainability hotspot count remains 8.

## Evidence

- `python -m pytest tests\unit\services\query_service\repositories\test_operations_repository.py -q`
  => `67 passed`
- `python -m pytest tests\integration\services\query_service\test_int_operations_service.py -q -k "valuation_jobs"`
  => `4 passed, 14 deselected`
- `python -m radon cc src\services\query_service\app\repositories\operations_repository.py -s`
  => `_apply_valuation_job_scope - A (3)` and valuation scope helpers A-ranked
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
repository scope-helper refactor with repository-local architecture and quality evidence; it does
not change operator-facing runtime behavior, API surface, onboarding flow, or wiki-owned product
truth.
