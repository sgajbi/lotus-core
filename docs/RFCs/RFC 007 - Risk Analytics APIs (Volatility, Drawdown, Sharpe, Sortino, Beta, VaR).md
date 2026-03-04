# RFC 007 - Risk Analytics APIs (Volatility, Drawdown, Sharpe, Sortino, Beta, VaR)

| Metadata | Value |
| --- | --- |
| Status | Archived |
| Created | Historical RFC (date not recorded in this repository) |
| Last Updated | 2026-03-04 |
| Owners | lotus-risk (authoritative owner) |
| Depends On | N/A in lotus-core |
| Scope | Archived from `lotus-core`; owned by `lotus-risk` |

## Executive Summary

RFC 007 originally defined risk analytics API capabilities.
Ownership has moved out of lotus-core; this file remains as a migration pointer with rationale.

## Original Requested Requirements (Preserved)

Historically, RFC 007 requested:
1. Risk analytics endpoints and contract definitions for portfolio risk metrics.
2. Correctness and consistency semantics for risk outputs.
3. API-level ownership for serving these analytics.

## Current Implementation Reality

1. Risk analytics API ownership is no longer in lotus-core.
2. Lotus-core treats this RFC as archived and points to lotus-risk as source of truth.

Authoritative location:
- `lotus-risk/docs/migrations/from-lotus-core/RFC 007 - Risk Analytics APIs (Volatility, Drawdown, Sharpe, Sortino, Beta, VaR).md`

## Requirement-to-Implementation Traceability

| Original Requirement | Current Implementation in lotus-core | Evidence |
| --- | --- | --- |
| Serve risk analytics API surface from lotus-core | De-owned from lotus-core | RFC classification and migration decision |
| Maintain risk analytics contract authority | Authority moved to lotus-risk | authoritative location above |
| Preserve migration context for integrators | Kept as archived pointer file | this archived RFC file |

## Design Reasoning and Trade-offs

1. **Why move ownership**: risk analytics evolved into dedicated domain ownership better aligned with lotus-risk boundaries.
2. **Why keep an archived stub**: prevents silent loss of lineage and helps callers migrate with explicit context.
3. **Trade-off**: temporary dual-reference overhead during migration period.

## Gap Assessment

For lotus-core scope, no implementation gap remains because capability ownership moved out of repository.

## Deviations and Evolution Since Original RFC

1. Risk analytics no longer belongs to lotus-core runtime/API ownership.
2. Cross-app decomposition split core data platform responsibilities from risk analytics domain responsibilities.

## Proposed Changes

1. Keep this RFC archived in lotus-core as a durable compatibility pointer.
2. Route all active risk analytics RFC evolution to lotus-risk.

## Test and Validation Evidence

1. Repository ownership/migration evidence:
   - archived status in lotus-core RFC set
   - authoritative RFC in lotus-risk repository

## Original Acceptance Criteria Alignment

Original acceptance moved to lotus-risk scope. In lotus-core, acceptance is now migration completeness and pointer integrity.

## Rollout and Backward Compatibility

No lotus-core runtime behavior change from this documentation retrofit.

## Open Questions

1. Are any internal lotus-core docs/tests still referencing this RFC as active owner rather than archived owner?

## Next Actions

1. Keep this compatibility stub in lotus-core until all references point to lotus-risk.
2. Ensure future risk analytics RFC updates happen only in lotus-risk.
