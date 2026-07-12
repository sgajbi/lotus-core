# CR-211 - Support Overview Failed Window Alignment Review

Status: Hardened

## Scope
- `GET /support/portfolios/{portfolio_id}/overview`
- `SupportOverviewResponse`
- failed-job recency policy in the support overview

## Problem
The support overview already consumed recent failed-job counts from the repository summaries, but it still:
- hardcoded a 24-hour failed window in service calls
- hid the failed-job window policy from operators
- discarded the recent failed-job counts from the response contract

That made the overview less truthful than the underlying query logic and left another support-plane policy seam implicit.

## Fix
- Added `failed_window_hours` query support to the support overview route
- Added `failed_window_hours` to `SupportOverviewResponse`
- Surfaced recent failed-job counts for valuation, aggregation, and analytics export on the overview
- Wired the selected failed window through `OperationsService.get_support_overview(...)`
- Strengthened unit, router dependency, and OpenAPI contract tests

## Why This Matters
- support overview policy is now explicit and auditable for both stale-state and recent-failure calculations
- operators can see whether current terminal failure pressure is historical residue or recent active instability
- this removes another hidden support-plane policy seam instead of creating a second-class summary surface

## Evidence
- `src/services/query_control_plane_service/app/routers/operations.py`
- `src/services/query_service/app/dtos/operations_dto.py`
- `src/services/query_service/app/services/operations_service.py`
- `tests/unit/services/query_service/services/test_operations_service.py`
- `tests/integration/services/query_control_plane_service/test_operations_router_dependency.py`
- `tests/integration/services/query_control_plane_service/test_control_plane_app.py`
- `python scripts/openapi_quality_gate.py`
