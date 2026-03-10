# SELL Slice 3 - Calculation Pipeline and Invariant Hardening

This slice tightens SELL calculation semantics in the financial calculator engine with explicit invariant checks.

## Implemented in this slice

- Added SELL invariant error path helper (`SELL invariant violation: ...`).
- Enforced non-negative proceeds constraints:
  - `net_sell_proceeds_local >= 0`
  - `net_sell_proceeds_base >= 0`
- Enforced positive disposal consumption:
  - `consumed_quantity > 0`
- Enforced non-negative disposed cost basis:
  - `cogs_base >= 0`
  - `cogs_local >= 0`
- Enforced disposal sign semantics after calculation:
  - `net_cost <= 0`
  - `net_cost_local <= 0`

## Evidence

- Unit tests:
  - `tests/unit/services/calculators/cost_calculator_service/engine/test_cost_calculator.py`
    - negative proceeds is rejected with invariant error
    - non-positive consumed quantity is rejected with invariant error
    - existing SELL gain and dual-currency behavior remains covered

## Notes

- This slice hardens deterministic invariants without changing outward API contract fields.
- Full SELL decomposition/query contract expansion continues in subsequent slices.
