# RFC 043 - Lotus Core Snapshot Contract Hardening (Freshness, Lineage, Section Governance)

| Metadata | Value |
| --- | --- |
| Status | Partially Implemented |
| Created | 2026-02-24 |
| Last Updated | 2026-03-05 |
| Owners | `query-service` integration contracts |
| Depends On | RFC 036, RFC 044 |
| Scope | Snapshot metadata hardening and section-governance policy |

## Executive Summary

RFC 043 targeted stronger snapshot metadata and policy-governed section access.
Current implementation only partially aligns with the original request:
1. `core-snapshot` endpoint is implemented and mature for baseline/simulation sections.
2. Snapshot policy data structures exist in integration policy service.
3. But requested metadata fields (`freshness_status`, lineage refs, section-governance metadata in snapshot response) are not present in current `CoreSnapshotResponse`.
4. Requested strict policy gating on snapshot section requests is not enforced directly in `create_core_snapshot`.

Classification: `Partially implemented (requires enhancement)`.

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

Not yet implemented in snapshot response/flow:
1. No dedicated snapshot metadata block carrying freshness/lineage fields requested by RFC text.
2. No direct policy-aware section gating in `create_core_snapshot` path (no `403` strict rejection flow tied to section policy in that endpoint).

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
| Freshness/lineage metadata in snapshot response | Not fully implemented | `core_snapshot_dto.py` response schema |
| Section governance policy model | Partially implemented in integration policy service | `integration_service.py` |
| Strict-mode rejection for disallowed snapshot sections | Not implemented in core-snapshot router/service path | `integration.py` + `core_snapshot_service.py` |

## Design Reasoning and Trade-offs

1. Snapshot service prioritized deterministic data assembly and simulation correctness.
2. Policy logic evolved in a separate effective-policy surface, which improved diagnostics but left snapshot governance coupling incomplete.

Trade-off:
- Governance metadata and enforcement split across endpoints can confuse downstream consumers expecting a single policy-governed snapshot contract.

## Gap Assessment

Remaining deltas:
1. Add explicit snapshot metadata block for freshness/lineage/governance signals.
2. Enforce section allow-list policy in core-snapshot request processing with deterministic strict-mode behavior.
3. Resolve alignment with RFC-044 provenance strategy (`RFC-043-D01` + `RFC-044-D01` in `RFC-DELTA-BACKLOG`).

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

Partially aligned.

## Rollout and Backward Compatibility

No runtime change introduced by this documentation retrofit.

## Open Questions

1. Should snapshot policy enforcement be embedded in `core-snapshot` endpoint, or remain a two-step contract (`policy/effective` + caller-side filtering)?

## Next Actions

1. Resolve architecture decision on where section governance must be enforced.
2. Implement missing metadata/enforcement path or rebaseline RFC accordingly.
3. Keep status as `Partially Implemented` until snapshot governance/provenance deltas close.

