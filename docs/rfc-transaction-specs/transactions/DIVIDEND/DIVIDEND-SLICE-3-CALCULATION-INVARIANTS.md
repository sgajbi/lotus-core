# DIVIDEND Slice 3 - Calculation Invariants

This slice introduces explicit DIVIDEND calculation semantics in the cost engine instead of relying on generic income fallback behavior.

## Implemented in this slice

1. Added dedicated `DividendStrategy` in financial calculator cost logic.
2. Enforced deterministic DIVIDEND invariants:
 - `quantity == 0`
 - `price == 0`
 - `gross_transaction_amount > 0`
 - `net_cost == 0`
 - `net_cost_local == 0`
 - `realized_gain_loss == 0`
 - `realized_gain_loss_local == 0`
3. Explicitly kept lot-impact absent for DIVIDEND (no lot creation/consumption).
4. Updated characterization and unit tests to reflect canonical explicit-zero realized P&L semantics.

## Shared-doc conformance note

- `shared/06-common-calculation-conventions.md`:
 - explicit zero-vs-not-applicable realized P&L behavior is now defined and enforced.
- `shared/03-normative-rules-and-precedence.md`:
 - transaction-specific DIVIDEND invariants now override permissive generic strategy behavior.
- `shared/11-test-strategy-and-gap-assessment.md`:
 - invariant rules are covered with focused negative-path and positive-path unit tests.

## Evidence

- `src/services/calculators/cost_calculator_service/app/cost_engine/processing/cost_calculator.py`
- `tests/unit/services/calculators/cost_calculator_service/engine/test_cost_calculator.py`
- `tests/unit/transaction_specs/test_dividend_slice0_characterization.py`
