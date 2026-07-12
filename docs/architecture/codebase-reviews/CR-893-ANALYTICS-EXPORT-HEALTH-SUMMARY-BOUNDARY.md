# CR-893: Analytics Export Health Summary Boundary

Date: 2026-06-04

## Scope

Reduce `OperationsRepository` analytics export health-summary complexity without changing SQL
semantics, public repository methods, or API response contracts.

## Finding

`OperationsRepository.get_analytics_export_job_health_summary` was a B-ranked method that mixed
threshold calculation, analytics-export base statement scoping, lower-case status aggregation,
oldest open export lookup, query execution, and `ExportJobHealthSummary` row mapping.

That made the analytics export operations-readiness path harder to compare with the adjacent
support-job health helpers and harder to extend safely.

## Action

Extracted analytics export health boundaries:

- `_analytics_export_job_health_aggregate(...)` builds accepted, running, stale-running, failed,
  recent-failed, and oldest-open created-at aggregates.
- `_oldest_open_analytics_export_job(...)` finds the oldest accepted or running export job.
- `_analytics_export_job_health_result_select(...)` centralizes aggregate plus oldest-open
  selection.
- `_analytics_export_job_health_summary_from_row(...)` centralizes `ExportJobHealthSummary`
  mapping with existing nullable count behavior.
- `_get_analytics_export_job_health_summary(...)` centralizes query execution and summary mapping.

The public method now remains a table-specific wrapper that builds the scoped base statement and
delegates the shared analytics export health flow.

## Result

`get_analytics_export_job_health_summary` now reports `A (1)` instead of `B (6)` under Radon
cyclomatic complexity. The extracted analytics export health helpers also report A-ranked
complexity.

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
