# RFC 016 - Concentration Analytics Engine

| Metadata | Value |
| --- | --- |
| Status | Archived |
| Created | 2025-08-31 |
| Last Updated | 2026-03-04 |
| Owners | lotus-risk (authoritative risk analytics owner) |
| Depends On | RFC 056, RFC 057 |
| Scope | Archived from `lotus-core`; concentration analytics endpoint ownership moved out |

## Executive Summary

RFC 016 proposed an in-core concentration analytics engine and `POST /portfolios/{portfolio_id}/concentration`.
That endpoint is no longer a lotus-core capability. It is hard-disabled in lotus-core and directed to lotus-risk.

## Original Requested Requirements (Preserved)

Original RFC 016 requested:
1. On-demand concentration engine (issuer and bulk metrics, HHI, top-N).
2. In-core concentration endpoint contract.
3. Epoch-aware analytics consistency with portfolio state.
4. Observability and future expansion of concentration dimensions.

## Current Implementation Reality

1. Concentration endpoint in lotus-core is hard-disabled and returns migration guidance (`410 Gone`).
2. Target service is lotus-risk (`/analytics/risk/concentration`).
3. Legacy in-core concentration analytics modules were retired under RFC 057.

Evidence:
- `tests/e2e/test_concentration_pipeline.py`
- `docs/RFCs/RFC 056 - Remove Legacy Query Analytics and Reporting Endpoints.md`
- `docs/RFCs/RFC 057 - Lotus Core Directory Reorganization and Legacy Module Retirement.md`
- query-service legacy endpoint redirection behavior (`legacy_gone.py`)

## Requirement-to-Implementation Traceability

| Original Requirement | Current Implementation in lotus-core | Evidence |
| --- | --- | --- |
| In-core concentration API | De-owned and hard-disabled | e2e concentration tests |
| In-core concentration engine library | Retired as legacy module | RFC 057 execution notes |
| Epoch-aware concentration calculations in-core | Not applicable after de-ownership | ownership change |
| Migration guidance for callers | Implemented | `LOTUS_CORE_LEGACY_ENDPOINT_REMOVED` behavior |

## Design Reasoning and Trade-offs

1. **Why move ownership**: concentration is part of risk-analytics domain boundaries now owned by lotus-risk.
2. **Why hard-disable with guidance**: explicit migration path is safer than silent removal.
3. **Trade-off**: near-term consumer migration effort for cleaner long-term domain ownership.

## Gap Assessment

No lotus-core implementation gap remains for RFC 016 itself because feature ownership has moved out.

## Deviations and Evolution Since Original RFC

1. Domain decomposition under RFC 056/057 superseded the original in-core concentration implementation plan.
2. Concentration analytics remained a required business capability, but under lotus-risk ownership.

## Proposed Changes

1. Keep RFC 016 archived with full migration rationale.
2. Keep all active concentration analytics RFC evolution in lotus-risk.

## Test and Validation Evidence

1. Migration behavior evidence:
   - `tests/e2e/test_concentration_pipeline.py`
2. Ownership and retirement decisions:
   - RFC 056 and RFC 057 documents

## Original Acceptance Criteria Alignment

Original in-core acceptance criteria are superseded by ownership transfer.
Current lotus-core acceptance is correct migration behavior and absence of conflicting in-core concentration runtime.

## Rollout and Backward Compatibility

No runtime change from this documentation retrofit.

## Open Questions

1. Are any internal docs still treating concentration endpoint as an active lotus-core responsibility?

## Next Actions

1. Keep this RFC as archived pointer in lotus-core.
2. Ensure concentration analytics updates are maintained in lotus-risk only.
