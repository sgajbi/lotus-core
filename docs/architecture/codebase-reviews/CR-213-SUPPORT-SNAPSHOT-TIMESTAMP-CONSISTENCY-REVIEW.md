# CR-213 - Support Snapshot Timestamp Consistency Review

Status: Hardened

## Scope
- `SupportOverviewResponse`
- `OperationsService.get_support_overview(...)`
- `OperationsService.get_calculator_slos(...)`

## Problem
The support overview did not expose when the snapshot was generated, and both overview/SLO paths used multiple implicit `datetime.now(...)` calls while computing backlog ages.

That created two problems:
- operators could not see when the overview snapshot was taken
- one response could contain small internal time skew because age calculations and snapshot generation used different captured times

## Fix
- Added `generated_at_utc` to `SupportOverviewResponse`
- Captured one `generated_at_utc` timestamp per support overview response and reused it for backlog-age calculations
- Reused one captured `generated_at_utc` timestamp in calculator SLO generation instead of calling `datetime.now(...)` again at response assembly time
- Strengthened unit, router dependency, and OpenAPI contract tests

## Why This Matters
- support snapshots are now timestamped explicitly
- backlog ages and generated timestamps are derived from one consistent clock capture per response
- this makes the support plane more trustworthy during incident triage and removes subtle time-skew behavior from operator-facing summaries

## Evidence
- `src/services/query_service/app/dtos/operations_dto.py`
- `src/services/query_service/app/services/operations_service.py`
- `tests/unit/services/query_service/services/test_operations_service.py`
- `tests/integration/services/query_control_plane_service/test_operations_router_dependency.py`
- `tests/integration/services/query_control_plane_service/test_control_plane_app.py`
- `python scripts/openapi_quality_gate.py`
