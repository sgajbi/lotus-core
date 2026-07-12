# CR-227 - Support Summary Job Correlation Drill-Through Review

Status: Hardened

## Scope
- `JobHealthSummary`
- `SupportOverviewResponse`
- `CalculatorSloBucket`
- valuation and aggregation backlog summary projection in `OperationsRepository` and `OperationsService`

## Problem
The support overview and calculator SLO already exposed the oldest open valuation and aggregation job ids, but they still hid the durable correlation handles operators use to move directly into logs and downstream event traces.

That left summary surfaces only half-drillable: operators could identify the owning durable row, but still needed a second pivot to recover the correlation context that actually anchors runtime investigation.

## Fix
- Extended `JobHealthSummary` with:
  - `oldest_open_job_correlation_id`
  - `oldest_open_security_id`
- Extended valuation oldest-job projection to return:
  - durable job id
  - security id
  - correlation id
- Extended aggregation oldest-job projection to return:
  - durable job id
  - correlation id
- Surfaced the new fields through:
  - `SupportOverviewResponse`
  - `CalculatorSloBucket`
- Strengthened repository, service, router dependency, and OpenAPI tests to prove the new contract end to end

## Why This Matters
- summary and SLO surfaces are now directly usable for log drill-through
- valuation backlog summaries now expose both the owning security and the owning correlation handle
- operators can move from overview or SLO to durable job row and correlated logs without an extra discovery call

## Evidence
- `src/services/query_service/app/repositories/operations_repository.py`
- `src/services/query_service/app/dtos/operations_dto.py`
- `src/services/query_service/app/services/operations_service.py`
- `tests/unit/services/query_service/repositories/test_operations_repository.py`
- `tests/unit/services/query_service/services/test_operations_service.py`
- `tests/integration/services/query_control_plane_service/test_operations_router_dependency.py`
- `tests/integration/services/query_control_plane_service/test_control_plane_app.py`
- `python -m pytest tests/unit/services/query_service/repositories/test_operations_repository.py tests/unit/services/query_service/services/test_operations_service.py tests/integration/services/query_control_plane_service/test_operations_router_dependency.py tests/integration/services/query_control_plane_service/test_control_plane_app.py -q`
- `python scripts/openapi_quality_gate.py`
- `python -m ruff check src/services/query_service/app/dtos/operations_dto.py src/services/query_service/app/repositories/operations_repository.py src/services/query_service/app/services/operations_service.py tests/unit/services/query_service/repositories/test_operations_repository.py tests/unit/services/query_service/services/test_operations_service.py tests/integration/services/query_control_plane_service/test_operations_router_dependency.py tests/integration/services/query_control_plane_service/test_control_plane_app.py`
