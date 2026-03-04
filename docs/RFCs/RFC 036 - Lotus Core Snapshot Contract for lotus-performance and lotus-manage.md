# RFC 036 - Lotus Core Snapshot Contract for lotus-performance and lotus-manage

| Metadata | Value |
| --- | --- |
| Status | Implemented |
| Created | 2026-02-23 |
| Last Updated | 2026-03-04 |
| Owners | `query-service` integration contracts |
| Depends On | RFC 036 baseline, RFC 043 hardening, RFC 049 analytics de-ownership |
| Scope | Canonical versioned snapshot boundary for downstream consumers |

## Executive Summary

RFC 036 introduced a lotus-core-owned snapshot contract for downstream systems.
The capability is implemented and materially evolved beyond the initial v1 concept:
1. Canonical endpoint exists and is test-covered.
2. Request supports as-of date, section controls, and consumer-system context.
3. Response includes contract metadata, policy provenance, freshness/lineage signals, and governed section payloads.
4. Snapshot supports baseline and simulation contexts with validation and conflict handling.

Classification: `Fully implemented and aligned`.

## Original Requested Requirements (Preserved)

Original RFC 036 requested:
1. Versioned snapshot endpoint under `/integration/portfolios/{portfolio_id}/core-snapshot`.
2. As-of control and consumer-aware section selection.
3. Stable lotus-core boundary for lotus-performance and lotus-manage.
4. Evolution path for stronger governance and metadata.

## Current Implementation Reality

Implemented:
1. Endpoint exists with explicit validation/error mappings (`400/404/409/422`).
2. Contracted DTOs and service logic support:
   - `as_of_date`,
   - section selection,
   - snapshot modes (baseline/simulation),
   - consumer and policy context.
3. Section-level governance and unavailable-section behavior are enforced.
4. Unit and integration tests cover router behavior and service decision logic.
5. Subsequent RFCs hardened freshness/lineage and ownership boundaries for analytics sections.

Evidence:
- `src/services/query_service/app/routers/integration.py`
- `src/services/query_service/app/dtos/core_snapshot_dto.py`
- `src/services/query_service/app/services/core_snapshot_service.py`
- `tests/unit/services/query_service/routers/test_integration_router.py`
- `tests/unit/services/query_service/services/test_core_snapshot_service.py`
- `tests/integration/services/query_service/test_main_app.py`
- `docs/RFCs/RFC 043 - Lotus Core Snapshot Contract Hardening (Freshness, Lineage, Section Governance).md`
- `docs/RFCs/RFC 049 - Lotus Core Snapshot Analytics De-Ownership and lotus-performance Input Contract.md`

## Requirement-to-Implementation Traceability

| Original Requirement | Current Implementation in lotus-core | Evidence |
| --- | --- | --- |
| Core snapshot endpoint | Implemented | integration router |
| Versioned contract boundary | Implemented through contract metadata and DTO contract fields | core snapshot DTO/service |
| As-of control and section scoping | Implemented with strict validation and policy-aware filtering | service logic + router tests |
| Consumer traceability | Implemented with consumer-system and policy provenance metadata | DTO/tests |
| Evolution path for hardening | Implemented via RFC 043 and later updates | RFC 043/049 references |

## Design Reasoning and Trade-offs

1. A single core-snapshot contract reduces duplicated query orchestration in consuming apps.
2. Section governance allows downstream consumers to request only needed data domains.
3. Explicit status/error mappings improve integration determinism and incident handling.

Trade-off:
- Contract richness increases schema complexity and requires strict compatibility governance as new sections are introduced.

## Gap Assessment

No high-value implementation gap identified for RFC 036 baseline scope.

## Deviations and Evolution Since Original RFC

1. Snapshot contract has evolved from simple v1 baseline to stronger policy and lineage semantics.
2. Analytics section ownership was refined by later RFCs to preserve domain boundaries with lotus-performance.

## Proposed Changes

1. Keep classification as `Fully implemented and aligned`.
2. Continue future evolution under dedicated follow-on RFCs (not by reopening RFC 036 baseline).

## Test and Validation Evidence

1. Router contract tests:
   - `tests/unit/services/query_service/routers/test_integration_router.py`
2. Snapshot service decision-path tests:
   - `tests/unit/services/query_service/services/test_core_snapshot_service.py`
3. Integration OpenAPI/runtime route checks:
   - `tests/integration/services/query_service/test_main_app.py`

## Original Acceptance Criteria Alignment

Aligned:
1. Snapshot endpoint and contract controls are implemented.
2. Requested hardening trajectory is realized in follow-on RFCs.

## Rollout and Backward Compatibility

No runtime change introduced by this documentation retrofit.

## Open Questions

1. None for RFC 036 baseline. Ongoing concerns are tracked in later snapshot-related RFCs.

## Next Actions

1. Maintain compatibility tests as new snapshot sections/contracts are added.

