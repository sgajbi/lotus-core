# FX Slice 5 - Swap Grouping and Deterministic Linkage

## Scope
This slice hardens `FX_SWAP` grouping so near-leg and far-leg semantics are explicit and replay-safe at the identifier layer.

## Delivered
1. Deterministic defaulting for:
 - `swap_event_id`
 - `near_leg_group_id`
 - `far_leg_group_id`
2. Far-leg contract exposure now anchors to `far_leg_group_id`, not the generic linked transaction group.
3. Validation rejects malformed swap grouping where near and far group ids collapse to the same value.

## Key Design Decisions
1. `swap_event_id` is the economic umbrella for the swap.
2. `near_leg_group_id` and `far_leg_group_id` are the concrete lifecycle groups.
3. Contract exposure belongs to the far leg because that is the leg that remains economically open beyond near settlement under the baseline model.

## Shared-Doc Conformance Note
Validated against:
1. `08-timing-semantics.md`
2. `09-idempotency-replay-and-reprocessing.md`
3. `12-canonical-modeling-guidelines.md`

## Residuals
1. This slice does not yet add a full replay permutation suite for out-of-order near/far arrival.
2. This slice does not yet synthesize near/far child rows from a single top-level swap instruction; it hardens canonical component ingestion and processing.

## Exit Evidence
1. `tests/unit/libs/portfolio_common/test_fx_linkage.py`
2. `tests/unit/libs/portfolio_common/test_fx_validation.py`

