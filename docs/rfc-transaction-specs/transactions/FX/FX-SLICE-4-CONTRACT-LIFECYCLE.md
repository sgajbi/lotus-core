# FX Slice 4 - Contract Instrument and Lifecycle

## Scope
This slice introduces the first durable contract-lifecycle implementation for canonical FX forwards and swaps.

## Delivered
1. Added synthetic `FX_CONTRACT` instrument support using `fx_contract_id` as the stable instrument/security key.
2. Added deterministic contract-instrument builder:
 - `build_fx_contract_instrument_event`
3. Extended instrument persistence to retain FX contract metadata:
 - `portfolio_id`
 - `trade_date`
 - pair currencies
 - buy/sell currencies
 - buy/sell notionals
 - `contract_rate`
4. Normalized `FX_CONTRACT_OPEN` and `FX_CONTRACT_CLOSE` rows onto the contract instrument id during FX enrichment.
5. Added explicit baseline FX processing path in cost-calculator so FX rows are persisted and published without falling into the generic BUY/SELL engine.
6. Added position-calculator lifecycle handling:
 - `FX_CONTRACT_OPEN` -> quantity `+1`
 - `FX_CONTRACT_CLOSE` -> quantity `-1`
 - `FX_CASH_SETTLEMENT_BUY` / `FX_CASH_SETTLEMENT_SELL` update cash-instrument balances using settlement amount, not canonical quantity

## Key Design Decisions
1. Contract lifecycle is represented as a position in a synthetic `FX_CONTRACT` instrument.
2. Quantity is used as open/closed state in the existing position engine:
 - `1` means open exposure
 - `0` means closed
3. Contract notionals and rate are stored on the instrument and transaction records, not forced into the generic position snapshot schema.
4. Spot remains policy-default `spot_exposure_model = NONE`; this slice does not auto-create spot contract exposure.
5. FX rows are persisted with explicit baseline realized-P&L fields when `fx_realized_pnl_mode = NONE`, rather than failing in the generic cost engine.

## Shared-Doc Conformance Note
Validated against:
1. `06-common-calculation-conventions.md`
 - quantity/cost semantics stay explicit and deterministic
2. `08-timing-semantics.md`
 - contract opens on trade date and closes on settlement/maturity date
3. `09-idempotency-replay-and-reprocessing.md`
 - contract instrument publication uses deterministic ids and replay-safe upsert behavior
4. `10-query-audit-and-observability.md`
 - contract metadata is retained in transaction and instrument persistence surfaces
5. `12-canonical-modeling-guidelines.md`
 - no aliases introduced; `FX_CONTRACT` is explicit canonical vocabulary

## What This Slice Does Not Yet Do
1. It does not yet implement swap-specific near/far orchestration behavior beyond stable identifiers.
2. It does not yet implement MTM/unrealized valuation for `FX_CONTRACT`.
3. It does not yet implement advanced realized FX P&L modes.

## Exit Evidence
1. `tests/unit/libs/portfolio_common/test_fx_contract_instrument.py`
2. `tests/unit/libs/portfolio_common/test_fx_linkage.py`
3. `tests/unit/services/calculators/position_calculator/core/test_position_logic.py`
4. `tests/unit/services/calculators/cost_calculator_service/consumer/test_cost_calculator_consumer.py`
5. `tests/integration/services/persistence_service/repositories/test_repositories.py`
6. `alembic/versions/be45fa67b890_feat_add_fx_contract_instrument_fields.py`
