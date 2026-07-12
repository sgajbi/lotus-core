# CR-216 - Support Listing Stale Threshold Semantics Review

Status: Hardened

## Scope
- `OperationsService` stale classification helpers
- valuation, aggregation, analytics export, replay key, and replay job support listings

## Problem
Support listings exposed `stale_threshold_minutes` in the request and response contract, but the shared stale classifier in `OperationsService` still used a hidden hardcoded 15-minute threshold.

That meant a caller could request a different threshold, see it echoed back in the response, and still receive stale-state classification derived from the old default.

## Fix
- Removed the hidden class-level 15-minute stale threshold from the stale-classification path
- Added `stale_threshold_minutes` to the shared support stale helpers and support job record builder
- Wired caller-selected stale thresholds through valuation, aggregation, analytics export, replay key, and replay job support listing classification
- Added targeted unit tests that prove custom thresholds change stale-state and operational-state classification

## Why This Matters
- support listing stale-state fields now honor the contract they advertise
- operators can trust that `stale_threshold_minutes` actually governs classification
- this closes a real false-contract bug on an operator-facing banking support surface

## Evidence
- `src/services/query_service/app/services/operations_service.py`
- `tests/unit/services/query_service/services/test_operations_service.py`
- `tests/unit/services/query_service/repositories/test_operations_repository.py`
- `tests/integration/services/query_control_plane_service/test_operations_router_dependency.py`
- `tests/integration/services/query_control_plane_service/test_control_plane_app.py`
- `python -m pytest tests/unit/services/query_service/services/test_operations_service.py tests/unit/services/query_service/repositories/test_operations_repository.py tests/integration/services/query_control_plane_service/test_operations_router_dependency.py tests/integration/services/query_control_plane_service/test_control_plane_app.py -q`
- `python scripts/openapi_quality_gate.py`
- `python -m ruff check src/services/query_service/app/services/operations_service.py tests/unit/services/query_service/services/test_operations_service.py tests/unit/services/query_service/repositories/test_operations_repository.py tests/integration/services/query_control_plane_service/test_operations_router_dependency.py tests/integration/services/query_control_plane_service/test_control_plane_app.py`
