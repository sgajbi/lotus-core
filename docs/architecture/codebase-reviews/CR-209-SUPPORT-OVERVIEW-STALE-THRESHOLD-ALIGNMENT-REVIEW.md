# CR-209 - Support Overview Stale Threshold Alignment Review

Status: Hardened

## Scope
- `GET /support/portfolios/{portfolio_id}/overview`
- `SupportOverviewResponse`
- `OperationsService.get_support_overview(...)`

## Problem
The support overview silently hardcoded a 15-minute stale threshold, while `calculator-slos` already allowed operators to choose a custom stale threshold.

That created policy drift between two support surfaces describing the same runtime state:
- overview stale counts could be computed with one threshold
- calculator SLO stale counts could be computed with another

The overview response also did not tell operators which threshold produced the stale-state values.

## Fix
- Added `stale_threshold_minutes` query support to the support overview route
- Added `stale_threshold_minutes` to `SupportOverviewResponse`
- Wired the selected threshold through `OperationsService.get_support_overview(...)`
- Replaced fixed 15-minute behavior in overview calculations with the passed threshold
- Strengthened unit, router dependency, and OpenAPI contract tests

## Why This Matters
- overview and calculator SLO now speak the same stale-policy language
- operators can intentionally choose and verify the threshold used for stale classification
- this removes a real support-plane policy drift bug rather than adding new surface area

## Evidence
- `src/services/query_control_plane_service/app/routers/operations.py`
- `src/services/query_service/app/dtos/operations_dto.py`
- `src/services/query_service/app/services/operations_service.py`
- `tests/unit/services/query_service/services/test_operations_service.py`
- `tests/integration/services/query_control_plane_service/test_operations_router_dependency.py`
- `tests/integration/services/query_control_plane_service/test_control_plane_app.py`
- `python scripts/openapi_quality_gate.py`
