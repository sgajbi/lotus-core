# RFC 058 - Generic Core Snapshot Contract for Stateful and Simulation Consumers

| Field | Value |
| --- | --- |
| Status | Partially Implemented |
| Created | 2026-02-27 |
| Last Updated | 2026-03-04 |
| Owners | lotus-core + downstream integration owners |
| Depends On | RFC 036, RFC 043, RFC 046A, RFC 049, RFC 057 |
| Related Standards | RFC-0067 OpenAPI/vocabulary governance; `docs/standards/rounding-precision.md` |
| Scope | Cross-repo |

## Executive Summary
RFC 058 defines one generic snapshot contract for baseline and simulation consumers. Core endpoint, DTOs, and service orchestration are implemented in lotus-core, including section-based baseline/projected/delta responses and simulation consistency checks.

Remaining alignment work is governance and policy-provenance integration: snapshot section policy/provenance behaviors are still split across separate endpoints and tracked in existing deltas (`RFC-043-D01`, `RFC-044-D01`).

## Original Requested Requirements (Preserved)
1. One consumer-agnostic endpoint: `POST /integration/portfolios/{portfolio_id}/core-snapshot`.
2. Explicit `snapshot_mode` (`BASELINE`/`SIMULATION`).
3. Comparable baseline/projected/delta sections.
4. Deterministic behavior for identical inputs.
5. Explicit valuation context (`as_of_date`, currencies, basis fields).
6. Decimal-safe monetary/weight modeling and governance-aligned OpenAPI/vocabulary.
7. Strong error contract (`400/404/409/422/500`).

## Current Implementation Reality
1. Snapshot endpoint exists in integration router with explicit error mappings.
2. Core snapshot DTOs include `snapshot_mode`, sections enum, simulation options, valuation context, and delta models.
3. Service validates portfolio/session existence, session-portfolio ownership, and expected-version conflicts.
4. Baseline/projected/delta/totals/enrichment sections are generated deterministically from repositories and sorted by security key.
5. OpenAPI contract includes required response codes and section semantics.
6. Policy provenance embedding and strict section-governance behavior remain tracked as separate open deltas.

## Requirement-to-Implementation Traceability
| Requirement | Current State | Evidence |
| --- | --- | --- |
| Generic snapshot endpoint | Implemented | `src/services/query_service/app/routers/integration.py` |
| Mode and sectioned contract | Implemented | `src/services/query_service/app/dtos/core_snapshot_dto.py` |
| Simulation consistency (`session_id`, portfolio match, expected_version) | Implemented | `src/services/query_service/app/services/core_snapshot_service.py`; `tests/unit/services/query_service/services/test_core_snapshot_service.py` |
| Baseline/projected/delta/totals/enrichment generation | Implemented | `src/services/query_service/app/services/core_snapshot_service.py` |
| Error contract coverage | Implemented | `src/services/query_service/app/routers/integration.py`; `tests/integration/services/query_service/test_main_app.py` |
| Policy provenance and strict section governance in snapshot payload | Partially implemented | `src/services/query_service/app/routers/integration.py` (`/integration/policy/effective` split model); `docs/RFCs/RFC-DELTA-BACKLOG.md` (`RFC-043-D01`, `RFC-044-D01`) |

## Design Reasoning and Trade-offs
1. One shared snapshot contract reduces duplicated orchestration in downstream apps.
2. Section-driven payload prevents over-fetch and allows consumer-specific assembly.
3. Keeping policy resolution in separate endpoint reduces payload bloat but increases two-step integration burden.

## Gap Assessment
1. Snapshot policy/provenance coupling is not fully unified in the snapshot response itself.
2. RFC text should explicitly align with implemented two-step policy model unless snapshot embedding is adopted.

## Deviations and Evolution Since Original RFC
1. Core contract is largely implemented and in production shape.
2. Governance expectations around section policy/provenance evolved into adjacent RFC deltas rather than being fully embedded here.

## Proposed Changes
1. Rebaseline RFC 058 around implemented contract as authoritative baseline.
2. Keep policy/provenance decisions as explicit follow-on closure criteria referencing `RFC-043-D01` and `RFC-044-D01`.

## Test and Validation Evidence
1. `tests/unit/services/query_service/services/test_core_snapshot_service.py`
2. `tests/integration/services/query_service/test_main_app.py`
3. `src/services/query_service/app/routers/integration.py`
4. `src/services/query_service/app/dtos/core_snapshot_dto.py`

## Original Acceptance Criteria Alignment
1. Deterministic baseline/simulation snapshots: aligned.
2. No consumer-specific endpoint fork: aligned.
3. Delta section availability: aligned.
4. Governance completeness around policy/provenance: partially aligned.

## Rollout and Backward Compatibility
1. Contract is additive and section-driven, enabling consumer migration without endpoint proliferation.
2. Policy/provenance behavior should remain stable once final model (embedded vs two-step) is ratified.

## Open Questions
1. Should policy provenance fields be embedded directly in `core-snapshot` responses?
2. Should section enforcement be strict in the snapshot endpoint itself or continue as caller-responsibility via `policy/effective`?

## Next Actions
1. Close `RFC-043-D01` and `RFC-044-D01` with final policy/provenance contract decision.
2. Update RFC 058 acceptance text once that decision is implemented.
