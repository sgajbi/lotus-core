# CR-260 Support Job List Snapshot Review

## Summary

The valuation, aggregation, and analytics export support listings already exposed
`generated_at_utc`, but their count and row queries were still live. That meant these support job
families could still drift underneath the advertised snapshot moment even after replay,
reconciliation, control-stage, and lineage listings had been hardened.

## Finding

- Class: support-plane correctness risk
- Consequence: one support job listing could report a `generated_at_utc` snapshot time while its
  total and row set still reflected durable updates written after that moment.

## Action Taken

- added optional `as_of` fences to:
  - `get_valuation_jobs_count(...)`
  - `get_valuation_jobs(...)`
  - `get_aggregation_jobs_count(...)`
  - `get_aggregation_jobs(...)`
  - `get_analytics_export_jobs_count(...)`
  - `get_analytics_export_jobs(...)`
- fenced all three job families by `updated_at <= as_of`
- updated `OperationsService` to pass each listing's `generated_at_utc` into both count and row
  queries for valuation, aggregation, and analytics export support listings
- strengthened repository SQL tests and service forwarding tests

## Evidence

- `python -m pytest tests/unit/services/query_service/repositories/test_operations_repository.py tests/unit/services/query_service/services/test_operations_service.py -q`
  - `104 passed`
- `python -m ruff check src/services/query_service/app/repositories/operations_repository.py src/services/query_service/app/services/operations_service.py tests/unit/services/query_service/repositories/test_operations_repository.py tests/unit/services/query_service/services/test_operations_service.py`
  - passed

## Follow-up

- keep applying snapshot fences only where the response already claims snapshot semantics
- keep list counts and list rows on the same durable cutoff whenever `generated_at_utc` is part of
  the operator contract
