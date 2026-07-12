# CR-071 Parameter Description Gate Review

## Scope
Close the remaining Swagger usability gap where query/path parameters still had examples but no descriptions on a subset of active endpoints.

## Findings
- After the prior Swagger passes, the only remaining parameter-description debt was concentrated in:
  - `query_service` lookup pagination filters
  - `event_replay_service` health and ingestion-operations query parameters
- The broader API surface was already clean enough to support a gate tightening.

## Changes
1. Added explicit parameter descriptions/examples to the remaining weak endpoints in:
   - `src/services/query_service/app/routers/lookups.py`
   - `src/services/event_replay_service/app/routers/ingestion_operations.py`
2. Extended `scripts/openapi_quality_gate.py` so operations now fail if any declared parameter lacks a description.
3. Added/updated unit coverage in `tests/unit/services/query_service/test_openapi_quality_gate.py`.

## Validation
- `python -m pytest tests/unit/services/query_service/test_openapi_quality_gate.py tests/integration/services/query_service/test_main_app.py tests/integration/services/event_replay_service/test_event_replay_app.py -q`
- `python scripts/openapi_quality_gate.py`
- direct schema sweep confirmed zero missing parameter descriptions across the active HTTP services

## Residual Risk
- New endpoints must document every declared parameter up front. The strengthened gate now enforces that and should catch regressions immediately.
