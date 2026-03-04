# RFC 047 - Position Materialization Guarantees for Multi-Portfolio Demo Data

| Metadata | Value |
| --- | --- |
| Status | Implemented |
| Created | 2026-02-24 |
| Last Updated | 2026-03-04 |
| Owners | `query-service`, demo bootstrap reliability |
| Depends On | RFC 046 demo data automation |
| Scope | Ensure demo portfolios materialize into query-visible holdings reliably |

## Executive Summary

RFC 047 addressed demo bootstrap correctness where transactions existed but holdings were missing for certain portfolios.
Current implementation includes protective query-side fallback and verification guardrails:
1. Position service falls back to ranked `position_history` when latest snapshots are absent.
2. Fallback rows are valuation-enriched using latest snapshot valuation map where available.
3. Demo data pack verification enforces per-portfolio position and holdings expectations, including `DEMO_DPM_EUR_001`.

Classification: `Fully implemented and aligned`.

## Original Requested Requirements (Preserved)

Original RFC 047 requested:
1. Explicit materialization invariant for net-open positions.
2. Deterministic multi-portfolio demo verification.
3. Hardening of query filtering/selection so valid positions are not silently dropped.

## Current Implementation Reality

Implemented:
1. Query position retrieval first uses latest snapshots and deterministically falls back to position-history ranked latest rows.
2. Fallback results receive valuation continuity through latest snapshot valuation map or cost-basis continuity when needed.
3. Demo data pack includes expectations requiring non-empty positions and validated holdings for each demo portfolio.
4. Unit tests cover snapshot fallback, valuation continuity behavior, and held-since logic.

Evidence:
- `src/services/query_service/app/services/position_service.py`
- `src/services/query_service/app/repositories/position_repository.py`
- `tests/unit/services/query_service/services/test_position_service.py`
- `tools/demo_data_pack.py`

## Requirement-to-Implementation Traceability

| Original Requirement | Current Implementation in lotus-core | Evidence |
| --- | --- | --- |
| Net-open holdings materialization behavior | Implemented via fallback latest-position-history retrieval | position service + repository |
| Deterministic demo multi-portfolio verification | Implemented with portfolio expectations and per-holding checks | `demo_data_pack.py` |
| Avoid silent drops from query assumptions | Implemented by explicit fallback path + ranking semantics | position service/repository + unit tests |

## Design Reasoning and Trade-offs

1. Snapshot-first + history-fallback pattern preserves correctness during asynchronous snapshot backfill windows.
2. Demo verification based on expected holdings catches materialization regressions early.

Trade-off:
- Fallback paths add complexity and require careful tests to avoid masking upstream pipeline defects.

## Gap Assessment

No high-value implementation gap identified for RFC 047 baseline scope.

## Deviations and Evolution Since Original RFC

1. Materialization guarantees are delivered primarily via query-service fallback and demo verification rather than only upstream calculator changes.

## Proposed Changes

1. Keep classification as `Fully implemented and aligned`.

## Test and Validation Evidence

1. Position fallback/continuity tests:
   - `tests/unit/services/query_service/services/test_position_service.py`
2. Demo portfolio materialization expectations:
   - `tools/demo_data_pack.py`

## Original Acceptance Criteria Alignment

Aligned.

## Rollout and Backward Compatibility

No runtime change introduced by this documentation retrofit.

## Open Questions

1. None for RFC 047 baseline scope.

## Next Actions

1. Continue monitoring demo materialization assertions as transaction scenarios evolve.
