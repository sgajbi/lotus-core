# RFC 044 - Lotus Core Policy Visibility Endpoint and Provenance Metadata

| Metadata | Value |
| --- | --- |
| Status | Implemented |
| Created | 2026-02-24 |
| Last Updated | 2026-03-05 |
| Owners | `query-service` integration contracts |
| Depends On | RFC 043 |
| Scope | Policy diagnostics endpoint and provenance metadata propagation |

## Executive Summary

RFC 044 introduced policy visibility requirements.
Current implementation is aligned:
1. `GET /integration/policy/effective` is implemented and returns policy provenance.
2. Provenance metadata model is implemented in integration DTOs and service logic.
3. Provenance metadata is now embedded in `core-snapshot` response governance metadata.

Classification: `Fully implemented and aligned`.

## Original Requested Requirements (Preserved)

Original RFC 044 requested:
1. Policy visibility endpoint for effective policy diagnostics.
2. Provenance fields in snapshot response metadata (`policy_version`, `policy_source`, `matched_rule_id`, `strict_mode`).
3. Backend-owned policy decisioning.

## Current Implementation Reality

Implemented:
1. `/integration/policy/effective` route exists and is backed by integration policy resolver.
2. Response includes `policy_provenance` with version/source/rule/strict attributes.
3. Unit tests cover policy resolution behavior and environment-policy parsing.

Fully implemented:
1. Core snapshot response schema includes governance metadata with policy provenance block.

Evidence:
- `src/services/query_service/app/routers/integration.py`
- `src/services/query_service/app/services/integration_service.py`
- `src/services/query_service/app/dtos/integration_dto.py`
- `src/services/query_service/app/dtos/core_snapshot_dto.py`
- `tests/unit/services/query_service/services/test_integration_service.py`
- `tests/unit/services/query_service/routers/test_integration_router.py`

## Requirement-to-Implementation Traceability

| Original Requirement | Current Implementation in lotus-core | Evidence |
| --- | --- | --- |
| Effective policy diagnostics endpoint | Implemented | `integration.py` route + service |
| Provenance metadata model | Implemented in policy endpoint response | `integration_dto.py` |
| Provenance fields in core-snapshot response | Implemented in snapshot governance metadata | `core_snapshot_dto.py`; `integration.py`; `core_snapshot_service.py` |

## Design Reasoning and Trade-offs

1. Dedicated policy diagnostics endpoint improves operator support workflows.
2. Keeping policy decisioning backend-owned reduces client complexity.

Trade-off:
- When snapshot responses omit policy provenance, clients need an extra call to correlate policy decisions.

## Gap Assessment

No blocking delta remains for RFC-044 scope.

## Deviations and Evolution Since Original RFC

1. Policy visibility endpoint is in place and strong.
2. Snapshot metadata propagation goal is now implemented through `CoreSnapshotResponse.governance.policy_provenance`.

## Proposed Changes

1. Keep classification as `Fully implemented and aligned`.
2. Maintain compatibility and regression checks as policy contract evolves.

## Test and Validation Evidence

1. `tests/unit/services/query_service/services/test_integration_service.py`
2. `tests/unit/services/query_service/routers/test_integration_router.py`

## Original Acceptance Criteria Alignment

Aligned.

## Rollout and Backward Compatibility

No runtime change introduced by this documentation retrofit.

## Open Questions

1. Is policy provenance in snapshot payload mandatory, or can `policy/effective` remain the sole provenance source?

## Next Actions

1. Maintain regression coverage for provenance propagation in snapshot response contracts.

