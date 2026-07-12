# CR-895: Lineage Keys Query Boundary

Date: 2026-06-04

## Scope

Reduce `OperationsRepository` lineage key query complexity without changing SQL semantics, public
repository methods, or API response contracts.

## Finding

`OperationsRepository.get_lineage_keys` was the final B-ranked method in `operations_repository.py`.
It mixed normalized security filtering, correlated latest position-history date lookup, correlated
latest daily snapshot date lookup, lateral valuation job lookup, artifact-gap policy, lineage
priority policy, result selection, reprocessing-key filtering, pagination, and execution in one
method.

That made a core operations-readiness and traceability query harder to review and harder to extend
without risking lineage ordering or as-of semantics.

## Action

Extracted lineage key query boundaries:

- `_lineage_latest_date_subquery(...)` builds correlated latest-date subqueries for history and
  daily snapshot evidence.
- `_lineage_artifact_gap_case(...)` centralizes artifact-gap policy.
- `_lineage_priority_case(...)` centralizes lineage ordering priority.
- `_lineage_keys_select(...)` centralizes the lineage key projection and valuation lateral join.

The public method now normalizes request filters, composes the helper SQL fragments, applies the
existing reprocessing-key scope, and executes the paginated query.

## Result

`get_lineage_keys` now reports `A (4)` instead of `B (6)` under Radon cyclomatic complexity. The
extracted lineage helper methods also report A-ranked complexity.

This removes the remaining B-ranked method from `operations_repository.py`. The module still
reports `C (0.00)` under Radon maintainability, so the source C-hotspot count remains 8.

## Evidence

Validation commands:

- `python -m pytest tests\unit\services\query_service\repositories\test_operations_repository.py -q`
  => `67 passed`
- `python -m ruff check src\services\query_service\app\repositories\operations_repository.py`
- `python -m radon cc src\services\query_service\app\repositories\operations_repository.py -s`
- `python -m radon mi src\services\query_service\app\repositories\operations_repository.py -s`

No integration selection was run for this slice. The change is an internal SQL-helper refactor
covered by operations repository SQL-shape unit tests; integration lineage coverage remains
available for broader PR-gate validation.

## Wiki Decision

No wiki source update is required. This is an internal repository helper refactor and does not
change an operator-facing contract, API contract, or runbook.
