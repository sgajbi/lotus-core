# RFC 035 - Lotus Core Responsibility and Integration Contract (lotus-performance and lotus-manage)

| Metadata | Value |
| --- | --- |
| Status | Partially Implemented |
| Created | 2026-02-23 |
| Last Updated | 2026-03-04 |
| Owners | Cross-app architecture (`lotus-core`, `lotus-performance`, `lotus-manage`) |
| Depends On | RFC 035 phase-1, RFC 036, RFC 037, RFC 038, RFC 057 |
| Scope | Responsibility boundaries and integration patterns across core, performance, and manage layers |

## Executive Summary

RFC 035 defines non-overlapping app responsibilities and required integration modes across lotus-core, lotus-performance, and lotus-manage.
In lotus-core, phase-1 integration onboarding capabilities are implemented (`portfolio-bundle`, upload adapter endpoints, integration contracts).

However, full cross-repo contract governance requested by RFC 035 is not fully closed:
1. The RFC mixes historical naming (`lotus-advise`) and current naming (`lotus-manage`) and needs normalized terminology.
2. Gateway-level canonical contract definitions for dual-mode operation remain distributed across multiple RFCs rather than one consolidated contract source.
3. Cross-repo glossary/provenance governance is partially present but not finalized as one enforceable platform contract.

Classification: `Partially implemented (requires enhancement)`.

## Original Requested Requirements (Preserved)

Original RFC 035 requested:
1. Explicit responsibility boundaries between lotus-core, lotus-performance, lotus-manage, and gateway/UI orchestration.
2. Dual integration pattern support:
   - direct-input mode for simulations/what-if,
   - lotus-core-connected mode for canonical state retrieval.
3. UI onboarding support through adapter upload/bundle APIs.
4. Non-overlap guardrails to prevent duplicate system-of-record behavior outside lotus-core.
5. Provenance-friendly integration contracts.

## Current Implementation Reality

Implemented in lotus-core:
1. `POST /ingest/portfolio-bundle` exists and fans mixed payloads into canonical ingestion topics.
2. Bulk file onboarding endpoints (`/ingest/uploads/preview`, `/ingest/uploads/commit`) exist for adapter workflows.
3. Integration contract surfaces exist (`/integration/...`, `/integration/capabilities`, `/integration/policy/effective`), including consumer context and policy provenance.
4. Adapter endpoints are explicitly guarded by adapter-mode controls and return deterministic `410` when disabled.

Partially implemented or pending at ecosystem level:
1. Single cross-repo source of truth for gateway composition contracts remains fragmented across RFCs and services.
2. Uniform glossary and provenance policy across all participating apps is still evolving.

Evidence:
- `src/services/ingestion_service/app/routers/portfolio_bundle.py`
- `src/services/ingestion_service/app/routers/uploads.py`
- `src/services/ingestion_service/app/adapter_mode.py`
- `src/services/query_service/app/routers/integration.py`
- `src/services/query_service/app/routers/capabilities.py`
- `src/services/query_service/app/services/capabilities_service.py`
- `tests/integration/services/ingestion_service/test_ingestion_routers.py`
- `tests/integration/services/query_service/test_capabilities_router_dependency.py`
- `tests/unit/services/query_service/services/test_integration_service.py`

## Requirement-to-Implementation Traceability

| Original Requirement | Current Implementation in lotus-core | Evidence |
| --- | --- | --- |
| Clear core ownership for canonical records | Implemented and reinforced via current router/service boundaries | query-service and ingestion-service routers |
| Dual integration pattern support | Implemented through capabilities contract and integration snapshot policy patterns | capabilities router/service; integration router |
| Upload onboarding pattern | Implemented (`portfolio-bundle`, `uploads preview/commit`) | ingestion routers + tests |
| Non-overlap guardrails | Partially enforced in architecture docs and adapter-mode semantics; cross-repo enforcement remains governance concern | RFC 057 references + adapter-mode guards |
| Provenance-friendly contracts | Partially implemented (correlation/request lineage, as-of dates, policy provenance present in key APIs) | integration DTO/service + ingestion job metadata paths |

## Design Reasoning and Trade-offs

1. Keeping adapter onboarding in lotus-core enables practical UI onboarding without violating canonical event flow.
2. Capabilities and policy endpoints reduce hardcoded assumptions in external consumers.
3. Explicit boundaries avoid accidental re-implementation of core persistence logic in downstream apps.

Trade-off:
- Adapter flexibility increases surface area and requires strict governance to prevent adapter endpoints from becoming unintended primary ingestion paths.

## Gap Assessment

Remaining deltas:
1. Consolidate cross-repo integration boundary contract into a platform-owned canonical artifact (including naming normalization and non-overlap rules).
2. Finalize cross-app vocabulary/provenance governance rules as enforceable checks.

## Deviations and Evolution Since Original RFC

1. Actual implementation added stronger policy/capability APIs than the initial phase-1 text.
2. Naming in the original RFC no longer reflects final app taxonomy (`lotus-advise` vs `lotus-manage`).

## Proposed Changes

1. Keep RFC 035 classified as `Partially implemented`.
2. Use this RFC as architectural boundary record; execute remaining cross-repo governance items in lotus-platform standards and contract tests.

## Test and Validation Evidence

1. Bundle/upload adapter integration tests:
   - `tests/integration/services/ingestion_service/test_ingestion_routers.py`
2. Capabilities contract integration tests:
   - `tests/integration/services/query_service/test_capabilities_router_dependency.py`
3. Integration service policy behavior unit tests:
   - `tests/unit/services/query_service/services/test_integration_service.py`

## Original Acceptance Criteria Alignment

Partially aligned:
1. Lotus-core phase-1 delivery is complete and robust.
2. Ecosystem-level boundary governance and standardized terminology still require closure.

## Rollout and Backward Compatibility

No runtime change introduced by this documentation retrofit.

## Open Questions

1. Should cross-repo non-overlap guardrails be enforced via automated schema/API ownership checks in lotus-platform CI?

## Next Actions

1. Track remaining boundary-governance deltas in backlog.
2. Normalize terminology in related RFCs and architecture docs to current app naming.

