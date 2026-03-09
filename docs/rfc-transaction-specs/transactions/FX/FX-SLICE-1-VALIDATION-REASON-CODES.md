# FX Slice 1 - Validation and Reason-Code Foundation

## Scope
This slice establishes the canonical FX contract for validation, metadata carriage, and safe engine recognition.

## Delivered
1. Added FX business transaction types to the engine enum:
 - `FX_SPOT`
 - `FX_FORWARD`
 - `FX_SWAP`
2. Added canonical transaction-domain modules:
 - `portfolio_common.transaction_domain.fx_models`
 - `portfolio_common.transaction_domain.fx_reason_codes`
 - `portfolio_common.transaction_domain.fx_validation`
3. Added canonical metadata carriage through:
 - ingestion transaction DTO
 - transaction event model
 - transaction persistence schema
 - query transaction DTO
4. Added safe calculator guardrail so FX types do not use the generic default cost strategy.

## Canonical FX Foundation Fields Introduced
1. Business and component typing
 - `transaction_type`
 - `component_type`
 - `component_id`
 - `linked_component_ids`
2. Settlement linkage
 - `fx_cash_leg_role`
 - `linked_fx_cash_leg_id`
 - `settlement_status`
3. Pair and amount semantics
 - `pair_base_currency`
 - `pair_quote_currency`
 - `fx_rate_quote_convention`
 - `buy_currency`
 - `sell_currency`
 - `buy_amount`
 - `sell_amount`
 - `contract_rate`
4. Contract and swap linkage
 - `fx_contract_id`
 - `fx_contract_open_transaction_id`
 - `fx_contract_close_transaction_id`
 - `settlement_of_fx_contract_id`
 - `swap_event_id`
 - `near_leg_group_id`
 - `far_leg_group_id`
5. Policy and P&L semantics
 - `spot_exposure_model`
 - `fx_realized_pnl_mode`
 - realized capital / FX / total P&L local and base fields

## Validation Baseline in This Slice
1. Business type must be `FX_SPOT`, `FX_FORWARD`, or `FX_SWAP`.
2. Component type must be one of the canonical FX component types.
3. Quantity and price must remain zero in the canonical foundation.
4. Buy/sell currencies must differ.
5. Buy/sell amounts and contract rate must be strictly positive.
6. Quote convention must be explicit.
7. Cash settlement components must carry role and opposite-leg linkage.
8. Forwards/swaps and contract components must carry `fx_contract_id`.
9. Swaps must carry swap near/far grouping identifiers.
10. Realized capital P&L must be explicit zero for FX.

## Deferred to Later Slices
1. Actual FX settlement cashflow behavior
2. `FX_CONTRACT` position lifecycle
3. swap orchestration and timing rules
4. realized FX P&L calculation policies beyond validation and metadata carriage
5. downstream query views dedicated to FX lifecycle interpretation

## Exit Evidence
1. `tests/unit/libs/portfolio_common/test_fx_validation.py`
2. `tests/unit/transaction_specs/test_fx_slice0_characterization.py`
3. Alembic migration for FX transaction metadata fields
