# FX Slice 0 - Gap Assessment and Characterization Baseline

## Scope
This slice documents the current baseline before canonical FX transaction behavior is implemented.

## What Exists Today
1. `lotus-core` already ingests and serves FX rates and uses them in valuation, query, and timeseries conversion paths.
2. The generic transaction stack has strong canonical support for BUY/SELL, DIVIDEND, INTEREST, portfolio-level flows, and several corporate-action families.
3. Transaction linkage metadata (`economic_event_id`, `linked_transaction_group_id`) already exists and is reusable.

## What Does Not Exist Yet
1. No canonical FX business transaction types existed before RFC 082 execution.
2. No FX component taxonomy existed for:
 - `FX_CONTRACT_OPEN`
 - `FX_CONTRACT_CLOSE`
 - `FX_CASH_SETTLEMENT_BUY`
 - `FX_CASH_SETTLEMENT_SELL`
3. No canonical FX validation/reason-code module existed.
4. No persisted FX contract/swap linkage metadata existed in the `transactions` table.
5. No `FX_CONTRACT` lifecycle handling existed in cost/position/cashflow engines.
6. The existing `ADJUSTMENT` cash-leg model was only appropriate for BUY/SELL/DIVIDEND/INTEREST-style dual-leg patterns, not for FX.

## Characterization Findings Locked by Tests
1. Ingestion/query surfaces can now carry FX canonical metadata without yet implementing full calculator behavior.
2. FX business types are registered explicitly in the transaction enum.
3. Cost calculator behavior for FX is intentionally blocked with an explicit error instead of silently falling through the generic default strategy.

## Why This Matters
Allowing FX to route through the old default strategy would produce incorrect cost semantics immediately. The safe baseline is explicit non-support in calculators until the dedicated FX settlement and contract slices land.

## Exit Evidence
1. `tests/unit/transaction_specs/test_fx_slice0_characterization.py`
2. RFC 082 implementation plan
