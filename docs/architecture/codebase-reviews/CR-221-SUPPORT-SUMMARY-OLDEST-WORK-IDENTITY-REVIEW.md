# CR-221 - Support Summary Oldest Work Identity Review

Status: Hardened

## Scope
- `OperationsRepository` health summaries for replay, valuation, aggregation, and analytics export
- `OperationsService.get_support_overview(...)`
- `OperationsService.get_calculator_slos(...)`
- support-plane DTO/OpenAPI contracts

## Problem
The support overview and calculator SLO endpoints exposed backlog counts and oldest dates, but still hid the concrete durable work items behind those backlogs.

That forced operators into an immediate second pivot just to identify the oldest replay key, valuation job, aggregation job, or analytics export job responsible for the summary signal.

## Fix
- Extended replay, valuation, aggregation, and analytics export health summaries to carry the oldest actionable durable identity:
  - `oldest_reprocessing_security_id`
  - `oldest_open_job_id` for valuation and aggregation
  - `oldest_open_job_id` and `oldest_open_request_fingerprint` for analytics export
- Surfaced those fields in:
  - `SupportOverviewResponse`
  - `CalculatorSloBucket`
  - `ReprocessingSloBucket`
- Strengthened repository tests to prove the oldest-item query ordering is deterministic and uses the real durable sort keys
- Strengthened service, router dependency, and OpenAPI tests to prove the new contract end to end

## Why This Matters
- summary endpoints now identify the concrete durable row behind a backlog signal
- operators can move directly from overview/SLO to the owning work item without another discovery call
- the support plane is more operationally truthful and actionable, not just numerically descriptive

## Evidence
- `src/services/query_service/app/repositories/operations_repository.py`
- `src/services/query_service/app/services/operations_service.py`
- `src/services/query_service/app/dtos/operations_dto.py`
- `tests/unit/services/query_service/repositories/test_operations_repository.py`
- `tests/unit/services/query_service/services/test_operations_service.py`
- `tests/integration/services/query_control_plane_service/test_operations_router_dependency.py`
- `tests/integration/services/query_control_plane_service/test_control_plane_app.py`
- `python -m pytest tests/unit/services/query_service/repositories/test_operations_repository.py tests/unit/services/query_service/services/test_operations_service.py tests/integration/services/query_control_plane_service/test_operations_router_dependency.py tests/integration/services/query_control_plane_service/test_control_plane_app.py -q`
- `python scripts/openapi_quality_gate.py`
- `python -m ruff check src/services/query_service/app/dtos/operations_dto.py src/services/query_service/app/services/operations_service.py src/services/query_service/app/repositories/operations_repository.py tests/unit/services/query_service/repositories/test_operations_repository.py tests/unit/services/query_service/services/test_operations_service.py tests/integration/services/query_control_plane_service/test_operations_router_dependency.py tests/integration/services/query_control_plane_service/test_control_plane_app.py`
