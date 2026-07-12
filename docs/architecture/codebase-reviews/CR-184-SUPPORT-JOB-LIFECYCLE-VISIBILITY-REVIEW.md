# CR-184 - Support Job Lifecycle Visibility Review

## Summary

The support-plane job listing endpoints exposed durable valuation and aggregation rows, but
flattened away the timing detail needed to operate them safely. An operator could see that a job
was `PROCESSING`, yet could not tell from the listing whether that row was recently active or
already stale without jumping back to the aggregate overview counters.

## Findings

1. `SupportJobRecord` exposed status and retry count, but not the durable `updated_at` timestamp.
2. The same contract did not expose whether a `PROCESSING` row was stale under the support stale
   threshold that the overview and SLO surfaces already use.
3. That forced support/debug workflows to cross-reference multiple endpoints for one question:
   "which listed processing jobs are actually unhealthy?"

## Fix

The support job contract now includes:

- `updated_at`
- `is_stale_processing`

`OperationsService` computes `is_stale_processing` deterministically using the same 15-minute
support stale threshold already used by the overview/SLO surfaces.

## Why This Is Better

- Operators can inspect queue state directly from the listing endpoint.
- The list contract is now truthful about lifecycle freshness instead of only status labels.
- The stale-processing interpretation is centralized in one service-level helper rather than left to
  ad hoc client logic.

## Evidence

- `src/services/query_service/app/dtos/operations_dto.py`
- `src/services/query_service/app/services/operations_service.py`
- `tests/unit/services/query_service/services/test_operations_service.py`
- `tests/integration/services/query_control_plane_service/test_operations_router_dependency.py`
- `tests/integration/services/query_control_plane_service/test_control_plane_app.py`
