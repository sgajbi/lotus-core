# RFC 048 - One-Year Demo History and Valuation Continuity for lotus-performance UI

| Metadata | Value |
| --- | --- |
| Status | Implemented |
| Created | 2026-02-24 |
| Last Updated | 2026-07-19 |
| Owners | demo bootstrap + query-service valuation continuity |
| Depends On | RFC 046, RFC 047 |
| Scope | Extend demo horizon and guarantee non-null holdings valuation continuity in degraded paths |

## Executive Summary

RFC 048 objectives are implemented:
1. Demo data pack now generates rolling one-year business-date history.
2. Compose demo loader seeds the complete pack on first boot, skips unchanged retained data, and
   exposes explicit force refresh for intentionally dirty sample state.
3. Position query fallback path enriches valuation from latest snapshots when possible.
4. When snapshot valuation is absent, fallback valuation continuity uses cost-basis values to avoid null holdings valuation fields.

Classification: `Fully implemented and aligned`.

## Original Requested Requirements (Preserved)

Original RFC 048 requested:
1. One-year demo history generation.
2. Deterministic but time-distributed transaction activity.
3. Forced refresh behavior in startup bootstrap.
4. Valuation continuity for fallback holdings when snapshots lag.

The original automatic force-refresh request was superseded by the restart-idempotency correction
in #811. Explicit force refresh remains available without replaying unchanged sources on every
retained-volume restart.

## Current Implementation Reality

Implemented:
1. Demo bundle window is derived from `date.today() - 365 days` through current date using business-day generation.
2. Demo loader skips the complete unchanged pack on retained-volume restart and exposes explicit
   `DEMO_DATA_PACK_FORCE_INGEST=true` refresh control.
3. Position service fallback logic:
   - uses latest snapshot valuation map when available,
   - otherwise emits non-null valuation continuity using cost basis.
4. Unit tests explicitly validate fallback valuation continuity behavior.

Evidence:
- `tools/demo_data_pack.py`
- `docker-compose.yml` (`demo_data_loader` restart-idempotency and explicit force control)
- `src/services/query_service/app/services/position_service.py`
- `tests/unit/services/query_service/services/test_position_service.py`

## Requirement-to-Implementation Traceability

| Original Requirement | Current Implementation in lotus-core | Evidence |
| --- | --- | --- |
| One-year demo history | Implemented | `demo_data_pack.py` business date window |
| Restart-idempotent bootstrap with explicit force refresh | Implemented | compose loader command |
| Fallback valuation enrichment | Implemented | position service fallback valuation map usage |
| Non-null continuity when snapshots absent | Implemented | cost-basis fallback valuation path + unit tests |

## Design Reasoning and Trade-offs

1. One-year horizon enables realistic analytics windows for downstream UI/performance flows.
2. One complete-pack decision keeps retained restarts deterministic without publishing unchanged
   source history; operators retain an explicit complete refresh control for intentionally dirty
   sample state.
3. Cost-basis fallback avoids null-value UI failure while asynchronous snapshot materialization catches up.

Trade-off:
- Cost-basis fallback is continuity-safe but not a substitute for full mark-to-market valuation semantics.

## Gap Assessment

No high-value implementation gap identified for RFC 048 scope.

## Deviations and Evolution Since Original RFC

1. Verification workflow is embedded in demo data automation tooling rather than separate scripts.

## Proposed Changes

1. Keep classification as `Fully implemented and aligned`.

## Test and Validation Evidence

1. Position fallback valuation tests:
   - `tests/unit/services/query_service/services/test_position_service.py`
2. Demo data generator implementation:
   - `tools/demo_data_pack.py`

## Original Acceptance Criteria Alignment

Aligned.

## Rollout and Backward Compatibility

No runtime change introduced by this documentation retrofit.

## Open Questions

1. None for RFC 048 baseline scope.

## Next Actions

1. Monitor demo dataset size/runtime trade-offs as additional asset types are introduced.
