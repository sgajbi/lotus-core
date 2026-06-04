# CR-892: Support Job Health Summary Boundary

Date: 2026-06-04

## Scope

Reduce duplicated operations repository health-summary orchestration for valuation and aggregation
support jobs without changing SQL semantics, public repository methods, or API response contracts.

## Finding

`OperationsRepository.get_valuation_job_health_summary` and
`OperationsRepository.get_aggregation_job_health_summary` were B-ranked methods with nearly
identical health-summary flow:

- derive stale and failed-window thresholds,
- build a job-specific base statement,
- aggregate pending, processing, stale processing, failed, and recent failed counts,
- find the oldest open job,
- execute the joined aggregate query,
- map the row into `JobHealthSummary`.

The duplicated orchestration made the operations-readiness repository harder to review and more
expensive to extend consistently across support-job types.

## Action

Extracted shared support-job health boundaries:

- `_support_job_health_thresholds(...)` centralizes stale and failed-window cutoff calculation.
- `_support_job_health_result_select(...)` centralizes aggregate and oldest-open result selection.
- `_support_job_health_summary_from_row(...)` centralizes `JobHealthSummary` row mapping while
  preserving valuation security normalization and aggregation's `None` security field.
- `_get_support_job_health_summary(...)` centralizes base-subquery aggregation, oldest-open lookup,
  query execution, and DTO mapping.

Valuation and aggregation public methods now remain table-specific wrappers that build the correct
base statement and delegate the shared support-job health flow.

## Result

`get_valuation_job_health_summary` now reports `A (1)` instead of `B (6)` under Radon cyclomatic
complexity.

`get_aggregation_job_health_summary` now reports `A (1)` instead of `B (6)` under Radon
cyclomatic complexity.

The extracted support-job health helpers report A-ranked complexity. `operations_repository.py`
remains `C (0.00)` under Radon maintainability, so the source C-hotspot count remains 8.

## Evidence

Validation commands:

- `python -m pytest tests\unit\services\query_service\repositories\test_operations_repository.py -q`
  => `67 passed`
- `python -m ruff check src\services\query_service\app\repositories\operations_repository.py`
- `python -m radon cc src\services\query_service\app\repositories\operations_repository.py -s`
- `python -m radon mi src\services\query_service\app\repositories\operations_repository.py -s`
- `python -m radon mi src -s`

No integration selection was run for this slice. The change is an internal SQL-helper refactor
covered by operations repository SQL-shape unit tests.

## Wiki Decision

No wiki source update is required. This is an internal repository helper refactor and does not
change an operator-facing contract, API contract, or runbook.
