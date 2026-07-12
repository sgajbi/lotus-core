# CR-238 - Replay Key Watermark-Date Drill-Through Filter Review

Status: Hardened

## Scope
- replay-key support listing repository, service, and router
- support overview oldest replay watermark to listing drill-through path

## Problem
The support overview already exposed `oldest_reprocessing_watermark_date`, and replay-key rows already exposed `watermark_date`.

But the replay-key listing still could not filter by that same durable watermark handle.

That left the overview with a useful replay-backlog date signal, but no direct list-level drill-through path to the matching replay keys.

## Fix
- Added optional `watermark_date` filtering to:
  - `OperationsRepository.get_reprocessing_keys_count(...)`
  - `OperationsRepository.get_reprocessing_keys(...)`
  - `OperationsService.get_reprocessing_keys(...)`
  - `GET /support/portfolios/{portfolio_id}/reprocessing-keys`
- Updated route description and OpenAPI assertions so the watermark-date drill-through contract is explicit and governed
- Strengthened repository SQL tests, service forwarding tests, router dependency tests, and OpenAPI contract tests

## Why This Matters
- `oldest_reprocessing_watermark_date` from the support overview is now directly usable on the replay-key listing
- replay backlog summaries and replay-key rows now compose cleanly instead of leaving a dead-end oldest-date signal
- this keeps replay support aligned with the same drill-through standard now applied across replay security ids, replay job ids, and correlation handles

## Evidence
- `src/services/query_service/app/repositories/operations_repository.py`
- `src/services/query_service/app/services/operations_service.py`
- `src/services/query_control_plane_service/app/routers/operations.py`
- `tests/unit/services/query_service/repositories/test_operations_repository.py`
- `tests/unit/services/query_service/services/test_operations_service.py`
- `tests/integration/services/query_control_plane_service/test_operations_router_dependency.py`
- `tests/integration/services/query_control_plane_service/test_control_plane_app.py`
- `python -m pytest tests/unit/services/query_service/repositories/test_operations_repository.py tests/unit/services/query_service/services/test_operations_service.py tests/integration/services/query_control_plane_service/test_operations_router_dependency.py tests/integration/services/query_control_plane_service/test_control_plane_app.py -q`
- `python scripts/openapi_quality_gate.py`
- `python -m ruff check src/services/query_service/app/repositories/operations_repository.py src/services/query_service/app/services/operations_service.py src/services/query_control_plane_service/app/routers/operations.py tests/unit/services/query_service/repositories/test_operations_repository.py tests/unit/services/query_service/services/test_operations_service.py tests/integration/services/query_control_plane_service/test_operations_router_dependency.py tests/integration/services/query_control_plane_service/test_control_plane_app.py`
