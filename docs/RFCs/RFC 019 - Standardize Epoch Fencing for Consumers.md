# RFC 019 - Standardize Epoch Fencing for Consumers

| Metadata | Value |
| --- | --- |
| Status | Implemented |
| Created | 2025-09-01 |
| Last Updated | 2026-03-04 |
| Owners | `portfolio-common`, calculator consumers, `timeseries_generator_service` |
| Depends On | RFC 001 |
| Scope | Shared epoch-fencing utility and consumer adoption |

## Executive Summary

RFC 019 standardized stale-event protection by centralizing epoch-fencing behavior into a reusable utility. The implementation is complete and in active use:
1. `EpochFencer` is implemented in shared library code.
2. Reprocessing-aware consumers use it in message paths.
3. Standard metric/log behavior is emitted for stale drops.
4. Developer docs and tests cover usage and behavior.

## Original Requested Requirements (Preserved)

Original RFC 019 requested:
1. Create reusable `EpochFencer` in `portfolio-common`.
2. Remove duplicated/manual fencing logic in consumers.
3. Ensure standardized stale-event metric emission.
4. Add unit tests and usage documentation.

## Current Implementation Reality

Current behavior:
1. Shared utility exists: `portfolio_common.reprocessing.EpochFencer` and `FencedEvent` protocol.
2. `position_calculator`, `cashflow_calculator_service`, and `timeseries_generator_service` consumers call `EpochFencer.check(...)` before business logic.
3. Stale events increment `epoch_mismatch_dropped_total` with service and key labels.
4. Unit tests cover fresh/stale paths and consumer integration points.
5. Reprocessing developer guide documents required usage for new consumers.

Evidence:
- `src/libs/portfolio-common/portfolio_common/reprocessing.py`
- `src/libs/portfolio-common/portfolio_common/monitoring.py`
- `src/services/calculators/position_calculator/app/core/position_logic.py`
- `src/services/calculators/cashflow_calculator_service/app/consumers/transaction_consumer.py`
- `src/services/timeseries_generator_service/app/consumers/position_timeseries_consumer.py`
- `tests/unit/libs/portfolio-common/test_reprocessing.py`
- `tests/unit/services/calculators/position_calculator/core/test_position_logic.py`
- `tests/unit/services/calculators/cashflow_calculator_service/unit/consumers/test_cashflow_transaction_consumer.py`
- `tests/unit/services/timeseries_generator_service/timeseries-generator-service/consumers/test_position_timeseries_consumer.py`
- `docs/features/reprocessing_engine/05_Developer_Guide.md`

## Requirement-to-Implementation Traceability

| Original Requirement | Current Implementation in lotus-core | Evidence |
| --- | --- | --- |
| Shared utility abstraction | `EpochFencer` + `FencedEvent` in shared library | `reprocessing.py` |
| Consumer adoption | Position, cashflow, timeseries consumers call fencer | consumer paths + unit tests |
| Centralized stale metric behavior | `epoch_mismatch_dropped_total` incremented in fencer | `monitoring.py`; `reprocessing.py` |
| Documentation and testability | Unit tests + developer guide | `test_reprocessing.py`; feature guide |

## Design Reasoning and Trade-offs

1. Centralizing epoch comparison removes repeated, error-prone boilerplate.
2. Embedding metric/log behavior in one place improves observability consistency.
3. Protocol-based event contract keeps utility generic across services.

Trade-off:
- Each check requires state lookup; this is accepted to preserve correctness under replay races.

## Gap Assessment

No material gap remains for RFC 019 in the current architecture.

## Deviations and Evolution Since Original RFC

1. Adoption includes both calculator and downstream consumer paths.
2. RFC 001 and RFC 004 documentation now treat shared fencing as the baseline implementation pattern.

## Proposed Changes

1. Keep RFC 019 classification as `Fully implemented and aligned`.
2. Continue compliance checks whenever new reprocessing-aware consumers are introduced.

## Test and Validation Evidence

1. Shared utility unit tests:
   - `tests/unit/libs/portfolio-common/test_reprocessing.py`
2. Consumer-level usage tests:
   - position/cashflow/timeseries unit suites listed above
3. End-to-end replay safety coverage:
   - `tests/e2e/test_rapid_reprocessing.py`

## Original Acceptance Criteria Alignment

Acceptance criteria are met:
1. Shared utility exists and is tested.
2. Target consumers are refactored to use it.
3. Stale drop metric behavior is standardized.
4. Developer guide exists.

## Rollout and Backward Compatibility

No runtime change introduced by this documentation retrofit.

## Open Questions

1. Should future non-calculator consumers that depend on epoched data be explicitly listed in a central compliance checklist?

## Next Actions

1. Maintain current baseline.
2. Gate future consumer additions on mandatory `EpochFencer` usage where epoched state applies.
