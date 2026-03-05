# INTEREST Slice 4 - Cash-Entry Mode, Withholding, and Linkage Accounting

## Scope

Slice 4 completes INTEREST cash-entry mode behavior parity with DIVIDEND and introduces withholding/net reconciliation validation primitives.

## Delivered Artifacts

- `src/services/calculators/cashflow_calculator_service/app/consumers/transaction_consumer.py`
  - EXTERNAL cash-entry bypass now supports both `DIVIDEND` and `INTEREST`
  - deterministic linkage enforcement for `external_cash_transaction_id`
- `src/services/calculators/cashflow_calculator_service/app/core/cashflow_logic.py`
  - INTEREST direction-aware sign handling (`INCOME` inflow, `EXPENSE` outflow)
- `src/libs/portfolio-common/portfolio_common/transaction_domain/interest_models.py`
  - canonical fields: `withholding_tax_amount`, `other_interest_deductions_amount`, `net_interest_amount`
- `src/libs/portfolio-common/portfolio_common/transaction_domain/interest_reason_codes.py`
  - reconciliation and withholding reason codes (`INTEREST_013`..`INTEREST_015`)
- `src/libs/portfolio-common/portfolio_common/transaction_domain/interest_validation.py`
  - non-negative withholding/deduction checks
  - net-interest reconciliation identity checks
- `tests/unit/services/calculators/cashflow_calculator_service/unit/consumers/test_cashflow_transaction_consumer.py`
  - INTEREST EXTERNAL mode skip + error-path tests
- `tests/unit/services/calculators/cashflow_calculator_service/unit/core/test_cashflow_logic.py`
  - INTEREST income/expense sign tests
- `tests/unit/libs/portfolio_common/test_interest_validation.py`
  - withholding and net-reconciliation tests

## Cash-Entry Mode Behavior

INTEREST now supports both canonical modes:

- `AUTO`: cashflow rule evaluation generates cashflow entry.
- `EXTERNAL`: auto cashflow generation is skipped; `external_cash_transaction_id` is mandatory.

Missing external linkage under `EXTERNAL` mode raises deterministic `ExternalCashLinkageError`.

## Reconciliation Identity

When `net_interest_amount` is provided, validator enforces:

`net_interest_amount = gross_transaction_amount - withholding_tax_amount - other_interest_deductions_amount`

All deduction components are constrained to non-negative values.

## Shared-Doc Conformance Note (Slice 4)

Validated shared standards for this slice:

- `shared/07-accounting-cash-and-linkage.md`: dual cash-entry modes and external-link enforcement implemented.
- `shared/06-common-calculation-conventions.md`: deterministic sign behavior for income/expense direction.
- `shared/05-common-validation-and-failure-semantics.md`: reconciliation reason codes and deterministic validation messages added.
- `shared/09-idempotency-replay-and-reprocessing.md`: EXTERNAL bypass path is idempotency-safe and marks event processed without auto cashflow side-effects.

## Residual Gaps (Expected for Later Slices)

- query/observability contract extensions are Slice 5.
