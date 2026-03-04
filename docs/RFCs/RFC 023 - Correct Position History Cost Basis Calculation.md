# RFC 023 - Correct Position History Cost Basis Calculation

| Metadata | Value |
| --- | --- |
| Status | Implemented |
| Created | 2025-09-02 |
| Last Updated | 2026-03-04 |
| Owners | `position_calculator_service` |
| Depends On | RFC 001, RFC 021 |
| Scope | Align position history cost-basis updates with authoritative transaction `net_cost` fields |

## Executive Summary

RFC 023 fixed a correctness issue in position cost-basis tracking for disposals.
The intended behavior was to treat `net_cost`/`net_cost_local` from upstream cost calculation as the authoritative COGS effect for `SELL`/`TRANSFER_OUT` events.

Current implementation is aligned:
1. Position logic applies additive `net_cost` semantics for disposal flows.
2. Unit tests explicitly guard against old proportional approximation behavior.
3. Position calculator docs now describe the corrected method.

## Original Requested Requirements (Preserved)

Original RFC 023 requested:
1. Remove proportional cost-basis reduction for sell-side events.
2. Apply authoritative event `net_cost` / `net_cost_local` for disposals.
3. Add targeted tests proving exact behavior.
4. Update position-calculator feature/methodology docs.

## Current Implementation Reality

Implemented behavior:
1. `calculate_next_position` uses additive `net_cost` and `net_cost_local` for `SELL` and `TRANSFER_OUT`.
2. Disposition path is now consistent with upstream cost engine output semantics.
3. Unit tests include explicit assertion that cost basis uses `net_cost` rather than proportional reduction.
4. Position calculator documentation reflects updated method.

Evidence:
- `src/services/calculators/position_calculator/app/core/position_logic.py`
- `tests/unit/services/calculators/position_calculator/core/test_position_logic.py`
- `docs/features/position_calculator/01_Feature_Position_Calculator_Overview.md`
- `docs/features/position_calculator/03_Methodology_Guide.md`

## Requirement-to-Implementation Traceability

| Original Requirement | Current Implementation in lotus-core | Evidence |
| --- | --- | --- |
| Remove proportional sell logic | No proportional math in disposal path | `position_logic.py` |
| Use event net-cost values as authority | `SELL`/`TRANSFER_OUT` add `transaction.net_cost` + `transaction.net_cost_local` | `position_logic.py` |
| Add correctness-focused tests | Explicit `test_calculate_next_position_for_sell_uses_net_cost` | `test_position_logic.py` |
| Refresh docs to corrected methodology | Updated feature + methodology guides | position calculator docs |

## Design Reasoning and Trade-offs

1. Single-source-of-truth principle: disposal COGS belongs to cost-calculator output, not a second approximation in position logic.
2. Simpler and more auditable position behavior by consuming canonical event fields.

Trade-off:
- Position calculator correctness is now more tightly coupled to upstream transaction enrichment quality, which is intentional architectural alignment.

## Gap Assessment

No material implementation gap remains for RFC 023 intent.

## Deviations and Evolution Since Original RFC

1. RFC 021 (FIFO/AVCO strategy support) strengthens the rationale for consuming authoritative net-cost output in RFC 023.
2. Downstream query contracts now inherit corrected position-history cost basis behavior.

## Proposed Changes

1. Keep RFC 023 classification as `Fully implemented and aligned`.
2. Preserve regression test for disposal-cost-basis invariants.

## Test and Validation Evidence

1. Unit coverage for corrected disposal behavior:
   - `tests/unit/services/calculators/position_calculator/core/test_position_logic.py`
2. Existing flow-level suites (reprocessing/valuation/timeseries) continue to validate no regression on dependent pipelines.

## Original Acceptance Criteria Alignment

Acceptance criteria are met for logic change, test coverage, and documentation updates.

## Rollout and Backward Compatibility

No runtime change introduced by this documentation retrofit.

## Open Questions

1. Should additional property-based invariants be added for disposal cost-basis transitions across varied transaction sequences?

## Next Actions

1. Keep current behavior as canonical baseline.
2. Maintain disposal-cost-basis regression assertions in unit and scenario test suites.
