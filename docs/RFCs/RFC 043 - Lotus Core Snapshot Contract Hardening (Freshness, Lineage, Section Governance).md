# RFC 043 - Lotus Core Snapshot Contract Hardening (Freshness, Lineage, Section Governance)

| Metadata | Value |
| --- | --- |
| Status | Implemented |
| Created | 2026-02-24 |
| Last Updated | 2026-03-05 |
| Owners | `query-service` integration contracts |
| Depends On | RFC 036, RFC 044 |
| Scope | Snapshot metadata hardening and section-governance policy |

## Executive Summary

RFC 043 targeted stronger snapshot metadata and policy-governed section access.
Current implementation now aligns with the original request:
1. `core-snapshot` endpoint is implemented and mature for baseline/simulation sections.
2. Snapshot governance now evaluates effective integration policy for consumer/tenant context.
3. `CoreSnapshotResponse` now carries freshness and governance metadata (including policy provenance).
4. Strict-mode section gating is enforced directly in `create_core_snapshot` with `403` behavior for blocked sections.

Classification: `Fully implemented and aligned`.

## Original Requested Requirements (Preserved)

Original RFC 043 requested:
1. Snapshot response metadata enrichment for freshness and lineage semantics.
2. Section governance controls via policy config (`LOTUS_CORE_INTEGRATION_SNAPSHOT_POLICY_JSON`).
3. Strict-mode section rejection behavior for disallowed section requests.

## Current Implementation Reality

Implemented:
1. `core-snapshot` endpoint and service support robust baseline/simulation section generation.
2. Integration policy framework (including `LOTUS_CORE_INTEGRATION_SNAPSHOT_POLICY_JSON`) exists and powers `/integration/policy/effective`.
3. Policy provenance structures are implemented in integration DTO/service layers.

Implemented in snapshot response/flow:
1. Snapshot freshness metadata block in `CoreSnapshotResponse.freshness`.
2. Snapshot governance metadata block in `CoreSnapshotResponse.governance`, including policy provenance.
3. Direct policy-aware section gating in `create_core_snapshot` with strict-mode `403` behavior and non-strict section filtering.

Evidence:
- `src/services/query_service/app/routers/integration.py`
- `src/services/query_service/app/services/core_snapshot_service.py`
- `src/services/query_service/app/dtos/core_snapshot_dto.py`
- `src/services/query_service/app/services/integration_service.py`
- `tests/unit/services/query_service/services/test_integration_service.py`
- `tests/unit/services/query_service/routers/test_integration_router.py`

## Requirement-to-Implementation Traceability

| Original Requirement | Current Implementation in lotus-core | Evidence |
| --- | --- | --- |
| Freshness/lineage metadata in snapshot response | Implemented (`freshness`, `governance`) | `core_snapshot_dto.py`; `core_snapshot_service.py` |
| Section governance policy model | Implemented via policy evaluation before snapshot assembly | `integration.py`; `integration_service.py` |
| Strict-mode rejection for disallowed snapshot sections | Implemented (`403` contract) | `integration.py`; `test_integration_router.py`; `test_main_app.py` |

## Design Reasoning and Trade-offs

1. Snapshot service prioritized deterministic data assembly and simulation correctness.
2. Policy logic evolved in a separate effective-policy surface, which improved diagnostics but left snapshot governance coupling incomplete.

Trade-off:
- Governance metadata and enforcement split across endpoints can confuse downstream consumers expecting a single policy-governed snapshot contract.

## Gap Assessment

No blocking delta remains for RFC-043 scope.

## Deviations and Evolution Since Original RFC

1. Policy visibility capability (RFC 044) advanced independently.
2. Core snapshot contract evolved around simulation + valuation context but not full metadata governance envelope described here.

## Proposed Changes

1. Keep classification as `Partially implemented`.
2. Deliver missing governance-enforcement and metadata fields as follow-on implementation, or revise RFC if governance scope moved to separate endpoint by design.

## Test and Validation Evidence

1. Snapshot router/service tests:
   - `tests/unit/services/query_service/routers/test_integration_router.py`
   - `tests/unit/services/query_service/services/test_core_snapshot_service.py`
2. Policy behavior tests:
   - `tests/unit/services/query_service/services/test_integration_service.py`

## Original Acceptance Criteria Alignment

Aligned.

## Rollout and Backward Compatibility

No runtime change introduced by this documentation retrofit.

## Open Questions

1. Should snapshot policy enforcement be embedded in `core-snapshot` endpoint, or remain a two-step contract (`policy/effective` + caller-side filtering)?

## Next Actions

1. Maintain regression coverage for snapshot governance/provenance in query-service test suites.

