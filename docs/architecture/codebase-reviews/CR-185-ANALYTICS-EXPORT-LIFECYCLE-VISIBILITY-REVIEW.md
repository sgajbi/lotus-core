# CR-185 - Analytics Export Lifecycle Visibility Review

## Summary

The analytics export support listing exposed durable export jobs, but it still forced operators to
infer lifecycle freshness from raw timestamps. The overview already exposed aggregate stale-running
counts, yet the row-level support contract did not tell an operator whether one specific `running`
job was stale or how old an open backlog item was.

## Findings

1. `AnalyticsExportJobRecord` exposed `created_at`, `started_at`, and `completed_at`, but not
   `updated_at`.
2. The contract did not expose whether a `running` export row was stale under the same
   support-plane stale threshold used elsewhere.
3. The contract did not expose per-row backlog age for `accepted` or `running` rows, which made it
   harder to distinguish one fresh queued item from one that had been waiting for a long time.

## Fix

The support-plane export record now includes:

- `updated_at`
- `is_stale_running`
- `backlog_age_minutes`

`OperationsService` computes the derived fields centrally so the listing endpoint and the aggregate
overview use the same lifecycle interpretation.

## Why This Is Better

- Operators can inspect one export row and immediately see whether it is stale.
- The support listing is now truthful about lifecycle freshness instead of being only timestamp-rich.
- Client code no longer needs to reimplement stale-running logic ad hoc.

## Evidence

- `src/services/query_service/app/dtos/operations_dto.py`
- `src/services/query_service/app/services/operations_service.py`
- `tests/unit/services/query_service/services/test_operations_service.py`
- `tests/integration/services/query_control_plane_service/test_operations_router_dependency.py`
- `tests/integration/services/query_control_plane_service/test_control_plane_app.py`
