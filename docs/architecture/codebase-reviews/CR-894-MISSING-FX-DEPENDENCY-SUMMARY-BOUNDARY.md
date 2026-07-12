# CR-894: Missing FX Dependency Summary Boundary

Date: 2026-06-04

## Scope

Reduce `OperationsRepository` missing historical FX dependency summary complexity without changing
SQL semantics, public repository methods, or API response contracts.

## Finding

`OperationsRepository.get_missing_historical_fx_dependency_summary` was a B-ranked method that
mixed base transaction/portfolio SQL construction, snapshot-as-of filtering, aggregate summary SQL,
sample-record SQL, database execution, and sample record normalization in one public method.

That made a portfolio readiness dependency check harder to review and harder to extend without
risking changes to the operator-facing readiness response.

## Action

Extracted missing historical FX dependency boundaries:

- `_missing_historical_fx_base_stmt(...)` builds the transaction/portfolio base scope.
- `_missing_historical_fx_aggregate_stmt(...)` builds the count and date-range aggregate.
- `_missing_historical_fx_sample_stmt(...)` builds the ordered sample query.
- `_missing_historical_fx_record_from_row(...)` centralizes security and currency normalization.
- `_missing_historical_fx_summary_from_rows(...)` centralizes summary assembly.

The public method now orchestrates the two repository reads and delegates SQL construction and
mapping to named helpers.

## Result

`get_missing_historical_fx_dependency_summary` now reports `A (1)` instead of `B (6)` under Radon
cyclomatic complexity. The extracted missing-FX helper methods also report A-ranked complexity.

`operations_repository.py` remains `C (0.00)` under Radon maintainability, so the source
C-hotspot count remains 8.

## Evidence

Validation commands:

- `python -m pytest tests\unit\services\query_service\repositories\test_operations_repository.py -q`
  => `67 passed`
- `python -m ruff check src\services\query_service\app\repositories\operations_repository.py`
- `python -m radon cc src\services\query_service\app\repositories\operations_repository.py -s`
- `python -m radon mi src\services\query_service\app\repositories\operations_repository.py -s`

No integration selection was run for this slice. The change is an internal SQL-helper refactor
covered by operations repository SQL-shape unit tests.

## Wiki Decision

No wiki source update is required. This is an internal repository helper refactor and does not
change an operator-facing contract, API contract, or runbook.
