# FX Slice 6 - Realized P&L Baseline Semantics

## Scope
This slice establishes deterministic baseline realized-P&L behavior for FX rows before advanced cash-lot treatment is introduced.

## Delivered
1. FX baseline processing path now persists FX rows without routing them through the generic BUY/SELL cost engine.
2. `fx_realized_pnl_mode = NONE`:
 - realized capital P&L local/base = `0`
 - realized FX P&L local/base = `0`
 - realized total P&L local/base = `0`
3. `fx_realized_pnl_mode = UPSTREAM_PROVIDED`:
 - capital P&L defaults to explicit zero when omitted
 - total P&L defaults to capital + FX when omitted
4. Canonical FX validation is enforced before persistence on the FX bypass path.

## Key Design Decisions
1. FX capital P&L remains explicit zero.
2. Baseline implementation supports `NONE` and `UPSTREAM_PROVIDED` deterministically.
3. `CASH_LOT_COST_METHOD` remains a later extension and is not simulated implicitly in this slice.

## Shared-Doc Conformance Note
Validated against:
1. `05-common-validation-and-failure-semantics.md`
2. `06-common-calculation-conventions.md`
3. `09-idempotency-replay-and-reprocessing.md`

## Residuals
1. No advanced cash-lot realized FX engine yet.
2. No MTM/unrealized contract valuation yet.

## Exit Evidence
1. `tests/unit/services/calculators/cost_calculator_service/consumer/test_cost_calculator_consumer.py`
2. `tests/unit/libs/portfolio_common/test_fx_validation.py`

