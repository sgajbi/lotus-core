# RFC 031 - Risk Service Correctness Hardening

| Metadata | Value |
| --- | --- |
| Status | Archived |
| Created | 2026-02-23 |
| Last Updated | 2026-03-04 |
| Owners | lotus-risk |
| Depends On | lotus-risk ownership stream |
| Scope | Compatibility stub in lotus-core; authoritative content moved to lotus-risk |

## Executive Summary

RFC 031 no longer belongs to lotus-core ownership.
Authoritative RFC content has been migrated to lotus-risk, and lotus-core keeps only a compatibility stub.

## Original Requested Requirements (Preserved)

Original RFC 031 requirements are maintained in the authoritative lotus-risk copy:
- `lotus-risk/docs/migrations/from-lotus-core/RFC 031 - Risk Service Correctness Hardening.md`

## Current Implementation Reality

1. Lotus-core file is a migration stub only.
2. Risk correctness hardening scope is owned and implemented/evolved in lotus-risk.

Evidence:
- `docs/RFCs/RFC 031 - Risk Service Correctness Hardening.md` (stub)
- Migration pointer to lotus-risk authoritative path

## Requirement-to-Implementation Traceability

| Original Requirement | Current Implementation in lotus-core | Evidence |
| --- | --- | --- |
| Risk service correctness hardening | Out-of-repo scope for lotus-core | local stub + migration pointer |
| RFC maintenance | Maintained in lotus-risk | authoritative path pointer |

## Design Reasoning and Trade-offs

1. Ownership separation prevents reintroducing risk-analytics responsibilities into lotus-core.
2. Stub retention preserves historical discoverability for existing references.

## Gap Assessment

No lotus-core implementation delta; this RFC is intentionally out-of-scope here.

## Deviations and Evolution Since Original RFC

1. RFC ownership migrated from lotus-core to lotus-risk.
2. Lotus-core retains compatibility link only.

## Proposed Changes

1. Keep RFC 031 archived in lotus-core.
2. Route all future RFC 031 updates to lotus-risk only.

## Test and Validation Evidence

Not applicable in lotus-core for this migrated scope.

## Original Acceptance Criteria Alignment

Superseded in lotus-core due to ownership migration.

## Rollout and Backward Compatibility

No runtime change introduced by this documentation retrofit.

## Open Questions

1. Should lotus-core maintain a centralized migration index for all migrated RFCs to reduce discovery friction?

## Next Actions

1. Keep stub intact.
2. Continue review loop against lotus-core-owned RFCs only.
