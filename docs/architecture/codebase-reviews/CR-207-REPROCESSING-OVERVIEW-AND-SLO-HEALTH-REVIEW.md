# CR-207 - Reprocessing Overview and SLO Health Review

Status: Hardened

## Scope
- support overview response
- calculator SLO response
- replay/reprocessing health summary query path

## Problem
Replay health in the support overview and calculator SLO surfaces lagged behind valuation and aggregation.

They exposed only:
- total active reprocessing keys

They did not expose:
- stale reprocessing keys
- oldest replay watermark in flight
- replay backlog age

That forced operators to pivot into the replay-key listing or manually infer replay pressure instead of seeing the health summary directly on the overview surfaces.

## Fix
- Added `ReprocessingHealthSummary` in `OperationsRepository`
- Added stale replay count and oldest replay watermark queries
- Enriched `SupportOverviewResponse` with:
  - `stale_reprocessing_keys`
  - `oldest_reprocessing_watermark_date`
  - `reprocessing_backlog_age_days`
- Enriched `ReprocessingSloBucket` with the same replay backlog and stale-key truth
- Strengthened unit, router dependency, and OpenAPI contract tests

## Why This Matters
- replay health is now visible on the same summary surfaces as valuation and aggregation
- operators can distinguish active replay from stale replay and quantify the replay backlog without leaving the overview path
- this keeps the support plane more balanced across the three durable processing families

## Evidence
- `src/services/query_service/app/repositories/operations_repository.py`
- `src/services/query_service/app/services/operations_service.py`
- `src/services/query_service/app/dtos/operations_dto.py`
- `tests/unit/services/query_service/services/test_operations_service.py`
- `tests/integration/services/query_control_plane_service/test_operations_router_dependency.py`
- `tests/integration/services/query_control_plane_service/test_control_plane_app.py`
- `python scripts/openapi_quality_gate.py`
