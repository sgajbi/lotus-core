# CR-258 Control Stage List Snapshot Review

## Summary

`PortfolioControlStageListResponse` was still a live count plus live rows with no explicit
snapshot timestamp, even after the surrounding support plane had been hardened to behave like a
coherent operator snapshot. That meant the control-stage listing could return rows updated after
the moment the caller thought they were observing, and the count and row set could drift during
one response.

## Finding

- Class: support-plane correctness risk
- Consequence: the control-stage listing was no longer aligned with the snapshot contract already
  adopted by replay, lineage, and support-summary surfaces. Operators could trust the newer
  surfaces more than the control-stage listing even though they are used together in the same
  triage flow.

## Action Taken

- added `generated_at_utc` to `PortfolioControlStageListResponse`
- added optional `as_of` fencing to:
  - `get_portfolio_control_stages_count(...)`
  - `get_portfolio_control_stages(...)`
- fenced both queries by `PipelineStageState.updated_at <= as_of`
- updated `OperationsService.get_portfolio_control_stages(...)` to:
  - capture one `generated_at_utc`
  - pass it into both repository queries
  - return it on the response
- strengthened repository, service, router dependency, and OpenAPI tests

## Evidence

- `python -m pytest tests/unit/services/query_service/repositories/test_operations_repository.py tests/unit/services/query_service/services/test_operations_service.py tests/integration/services/query_control_plane_service/test_operations_router_dependency.py tests/integration/services/query_control_plane_service/test_control_plane_app.py -q`
  - `153 passed`
- `python -m ruff check src/services/query_service/app/dtos/operations_dto.py src/services/query_service/app/repositories/operations_repository.py src/services/query_service/app/services/operations_service.py tests/unit/services/query_service/repositories/test_operations_repository.py tests/unit/services/query_service/services/test_operations_service.py tests/integration/services/query_control_plane_service/test_operations_router_dependency.py tests/integration/services/query_control_plane_service/test_control_plane_app.py`
  - passed

## Follow-up

- keep applying the same standard only where a list or summary already claims snapshot semantics
- avoid adding snapshot timestamps without also fencing the count and row queries that back them
