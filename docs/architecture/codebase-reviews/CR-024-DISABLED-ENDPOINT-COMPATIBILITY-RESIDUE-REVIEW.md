# CR-024 Disabled Endpoint Compatibility Residue Review

## Scope

Review stale disabled-endpoint compatibility helpers left behind after the
query/reporting/concentration de-ownership work.

## Finding

`src/services/query_service/app/routers/legacy_gone.py` was dead code.

- No production router imported or called it.
- No integration or E2E flow depended on it.
- Only a unit test and a few historical RFC documents still referenced it.

The actual enforced behavior now comes from:

- query-service not exposing those routes in active OpenAPI/runtime ownership
- shared E2E assertions that accept the approved disabled-route policy

Keeping the helper in-place implied a live compatibility contract that no
longer existed in runtime code.

## Action Taken

1. Deleted the dead helper and its unit test.
2. Updated historical RFCs so they no longer claim the helper is part of the
   current implementation reality.
3. Recorded the disabled-route behavior against the actual surviving evidence:
   route inventory and shared E2E assertions.

## Result

The query-service codebase no longer carries a fake compatibility surface for a
removed runtime behavior.

## Evidence

- Deleted: `src/services/query_service/app/routers/legacy_gone.py`
- Deleted: `tests/unit/services/query_service/routers/test_legacy_gone.py`
- Updated: `docs/RFCs/RFC 012 - Portfolio Review API.md`
- Updated: `docs/RFCs/RFC 016 - Concentration Analytics Engine.md`
- Updated: `docs/RFCs/RFC 034 - API Contract Decomposition and Vocabulary Alignment.md`
