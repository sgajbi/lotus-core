# CR-265 Support Health Summary Snapshot Fence Review

## Summary

The support overview and calculator SLO responses both expose `generated_at_utc`, but their
underlying health summary repository queries still evaluated live rows with no `as_of` fence. That
meant counts, stale/failure totals, and oldest backlog identities could still drift underneath a
timestamped response.

## Finding

- Class: support-plane correctness risk
- Consequence: the support overview and calculator SLO could claim one snapshot time while their
  replay, valuation, aggregation, and analytics export health summaries still reflected durable
  updates written after that moment.

## Action Taken

- widened all four health summary repository methods with optional `as_of`:
  - `get_reprocessing_health_summary(...)`
  - `get_valuation_job_health_summary(...)`
  - `get_aggregation_job_health_summary(...)`
  - `get_analytics_export_job_health_summary(...)`
- fenced both:
  - aggregate summary queries
  - oldest-item identity queries
  by `updated_at <= as_of`
- updated `OperationsService.get_support_overview(...)` and
  `OperationsService.get_calculator_slos(...)` to pass `generated_at_utc` into all four health
  summary calls
- strengthened repository SQL tests and service forwarding tests

## Evidence

- `python -m pytest tests/unit/services/query_service/repositories/test_operations_repository.py tests/unit/services/query_service/services/test_operations_service.py -q`
  - `103 passed`
- `python -m ruff check src/services/query_service/app/repositories/operations_repository.py src/services/query_service/app/services/operations_service.py tests/unit/services/query_service/repositories/test_operations_repository.py tests/unit/services/query_service/services/test_operations_service.py`
  - passed

## Follow-up

- keep applying the same standard to any repository summary that feeds a timestamped support
  response: the summary aggregates and the oldest-item selectors both need the same durable cutoff
