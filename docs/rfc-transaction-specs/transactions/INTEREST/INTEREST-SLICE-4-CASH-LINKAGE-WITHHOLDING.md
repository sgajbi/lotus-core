# INTEREST Slice 4 - Cash-Entry Mode, Withholding, and Linkage Accounting

## Scope

Slice 4 completes INTEREST cash-entry mode behavior parity with DIVIDEND and introduces withholding/net reconciliation validation primitives.

## Delivered Artifacts

- `src/services/portfolio_transaction_processing_service/app/application/cashflow_processing/use_case.py`
  - UPSTREAM_PROVIDED cash-entry bypass now supports both `DIVIDEND` and `INTEREST`
  - deterministic linkage enforcement for `external_cash_transaction_id`
- `src/services/portfolio_transaction_processing_service/app/domain/cashflow/calculation.py`
  - INTEREST direction-aware sign handling (`INCOME` inflow, `EXPENSE` outflow)
- `src/services/portfolio_transaction_processing_service/app/domain/transaction/booked.py`
  - canonical fields: `withholding_tax_amount`, `other_interest_deductions_amount`, `net_interest_amount`
- `src/services/portfolio_transaction_processing_service/app/domain/transaction/validation/reason_codes.py`
  - reconciliation and withholding reason codes (`INTEREST_013`..`INTEREST_015`)
- `src/services/portfolio_transaction_processing_service/app/domain/transaction/validation/income.py`
  - non-negative withholding/deduction checks
  - net-interest reconciliation identity checks
- `tests/unit/services/portfolio_transaction_processing_service/application/cashflow_processing/test_use_case.py`
  - INTEREST UPSTREAM_PROVIDED mode skip + error-path tests
- `tests/unit/services/portfolio_transaction_processing_service/domain/cashflow/test_calculation.py`
  - INTEREST income/expense sign tests
- `tests/unit/services/portfolio_transaction_processing_service/domain/transaction/validation/test_income.py`
  - withholding and net-reconciliation tests

## Cash-Entry Mode Behavior

INTEREST now supports both canonical modes:

- `AUTO_GENERATE`: cashflow rule evaluation generates cashflow entry.
- `UPSTREAM_PROVIDED`: auto cashflow generation is skipped; `external_cash_transaction_id` is mandatory.

Missing external linkage under `UPSTREAM_PROVIDED` mode raises deterministic `ExternalCashLinkageError`.

## Reconciliation Identity

When `net_interest_amount` is provided, validator enforces:

`net_interest_amount = gross_transaction_amount - withholding_tax_amount - other_interest_deductions_amount`

`net_interest_amount` is therefore before separately reported transaction fees. Settlement cash
applies the resolved fee exactly once: income subtracts the fee and expense adds the fee. Explicit
and derived net-interest source shapes must produce the same settlement amount. All deduction and
fee components are constrained to non-negative values.

## Shared-Doc Conformance Note (Slice 4)

Validated shared standards for this slice:

- `shared/07-accounting-cash-and-linkage.md`: dual cash-entry modes and external-link enforcement implemented.
- `shared/06-common-calculation-conventions.md`: deterministic sign behavior for income/expense direction.
- `shared/05-common-validation-and-failure-semantics.md`: reconciliation reason codes and deterministic validation messages added.
- `shared/09-idempotency-replay-and-reprocessing.md`: UPSTREAM_PROVIDED bypass path is idempotency-safe and marks event processed without auto cashflow side-effects.

## Residual Gaps (Expected for Later Slices)

- query/observability contract extensions are Slice 5.

