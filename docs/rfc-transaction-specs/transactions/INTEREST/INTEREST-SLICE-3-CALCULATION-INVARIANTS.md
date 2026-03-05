# INTEREST Slice 3 - Calculation Invariants and Direction Semantics

## Scope

Slice 3 hardens INTEREST calculation behavior in the cost engine and introduces a deterministic direction baseline.

## Delivered Artifacts

- `src/libs/financial-calculator-engine/src/logic/cost_calculator.py`
  - new `InterestStrategy` with explicit INTEREST invariants
  - explicit zero realized P&L semantics for INTEREST
  - baseline direction validation (`INCOME` or `EXPENSE`)
- `src/libs/portfolio-common/portfolio_common/transaction_domain/interest_models.py`
  - `interest_direction` field added to canonical model
- `src/libs/portfolio-common/portfolio_common/transaction_domain/interest_reason_codes.py`
  - `INTEREST_012_INVALID_INTEREST_DIRECTION`
- `src/libs/portfolio-common/portfolio_common/transaction_domain/interest_validation.py`
  - direction validation rule
- `tests/unit/libs/financial-calculator-engine/unit/test_cost_calculator.py`
  - INTEREST invariant and direction tests
- `tests/unit/libs/portfolio_common/test_interest_validation.py`
  - canonical direction validation tests
- `tests/unit/transaction_specs/test_interest_slice0_characterization.py`
  - updated to explicit zero realized P&L semantics

## Engine Invariants Enforced

`InterestStrategy` now enforces:

- `quantity == 0`
- `price == 0`
- `gross_transaction_amount > 0` (baseline absolute amount contract)
- `net_cost == 0` and `net_cost_local == 0`
- `realized_gain_loss == 0` and `realized_gain_loss_local == 0`
- `interest_direction` when supplied must be `INCOME` or `EXPENSE`

No lot creation/consumption occurs in INTEREST strategy.

## Direction Baseline

Baseline mapping is deterministic:

- default direction when omitted: `INCOME`
- supported explicit directions: `INCOME`, `EXPENSE`
- unknown direction values fail validation and engine invariants

This establishes canonical direction semantics without introducing new API endpoints.

## Shared-Doc Conformance Note (Slice 3)

Validated shared standards for this slice:

- `shared/05-common-validation-and-failure-semantics.md`: canonical direction validation reason code added.
- `shared/06-common-calculation-conventions.md`: explicit numeric invariant enforcement and deterministic zero realized P&L outputs.
- `shared/07-accounting-cash-and-linkage.md`: direction semantics prepared for downstream cashflow/accounting behavior slices.
- `shared/11-test-strategy-and-gap-assessment.md`: unit and characterization tests updated to reflect canonical semantics.

## Residual Gaps (Expected for Later Slices)

- cash-entry mode execution behavior and withholding/net reconciliation are Slice 4.
- query/observability contract extensions are Slice 5.
