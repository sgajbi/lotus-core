# CR-220 - Lineage Key Operational Priority Ordering Review

Status: Hardened

## Scope
- `OperationsRepository.get_lineage_keys(...)`
- lineage key support-plane ordering

## Problem
The lineage key listing already exposed server-owned health semantics such as `REPLAYING`, `VALUATION_BLOCKED`, `ARTIFACT_GAP`, and `HEALTHY`, but the repository query still ordered keys alphabetically by `security_id`.

That meant unhealthy keys could be buried behind healthy keys on the first page, making the support plane worse for triage than the hardened job listings.

## Fix
- Added severity-first ordering to lineage key repository queries
- Prioritized keys in this order:
  - `REPROCESSING`
  - artifact-gap keys with failed valuation context
  - other artifact-gap keys
  - everything else
- Kept deterministic tie-breaking with latest position-history date and `security_id`
- Strengthened repository tests to prove the generated SQL carries the severity ordering

## Why This Matters
- lineage key pagination now matches the operator semantics already exposed in the response contract
- unhealthy keys surface first instead of being hidden behind alphabetical order
- this makes the lineage support plane materially better for incident triage

## Evidence
- `src/services/query_service/app/repositories/operations_repository.py`
- `tests/unit/services/query_service/repositories/test_operations_repository.py`
- `python -m pytest tests/unit/services/query_service/repositories/test_operations_repository.py tests/unit/services/query_service/services/test_operations_service.py tests/integration/services/query_control_plane_service/test_operations_router_dependency.py tests/integration/services/query_control_plane_service/test_control_plane_app.py -q`
- `python scripts/openapi_quality_gate.py`
- `python -m ruff check src/services/query_service/app/repositories/operations_repository.py tests/unit/services/query_service/repositories/test_operations_repository.py tests/unit/services/query_service/services/test_operations_service.py tests/integration/services/query_control_plane_service/test_operations_router_dependency.py tests/integration/services/query_control_plane_service/test_control_plane_app.py`
