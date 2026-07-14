# INTEREST Slice 6 - Conformance Report

## Scope

This report closes RFC-070 execution by mapping `RFC-INTEREST-01` requirements to implementation evidence and suite wiring.

## Suite and CI Wiring

Delivered:

- `scripts/quality/test_manifest.py`
  - `transaction-interest-contract`
  - alias `transaction-interest-contract`
- `Makefile`
  - `test-transaction-interest-contract`
  - `test-transaction-interest-contract`
- `.github/workflows/ci.yml`
  - matrix includes `transaction-interest-contract`

## Requirement-to-Evidence Mapping

| RFC Requirement Area | Status | Evidence |
| --- | --- | --- |
| Canonical INTEREST validation taxonomy | COVERED | `src/services/portfolio_transaction_processing_service/app/domain/transaction/validation/reason_codes.py`, `src/services/portfolio_transaction_processing_service/app/domain/transaction/validation/income.py`, `tests/unit/services/portfolio_transaction_processing_service/transaction/test_income_validation.py` |
| Strict metadata validation | COVERED | `validate_interest_transaction(..., strict_metadata=True)`, `tests/unit/services/portfolio_transaction_processing_service/transaction/test_income_validation.py` |
| Deterministic linkage/policy enrichment | COVERED | `src/services/portfolio_transaction_processing_service/app/domain/transaction/booking_metadata.py`, `src/services/portfolio_transaction_processing_service/app/application/cost_basis_processing/execution.py`, `tests/unit/services/portfolio_transaction_processing_service/transaction/test_booking_metadata.py` |
| Calculation invariants (no qty/lot impact, explicit zero realized P&L) | COVERED | `src/services/portfolio_transaction_processing_service/app/domain/cost_basis/calculation/cost_basis_calculator.py` (`InterestStrategy`), `tests/unit/services/portfolio_transaction_processing_service/cost/test_cost_calculator.py` |
| Direction semantics (income vs expense baseline) | COVERED | `src/services/portfolio_transaction_processing_service/app/domain/transaction/booked.py`, `src/services/portfolio_transaction_processing_service/app/domain/transaction/validation/income.py`, `src/services/portfolio_transaction_processing_service/app/domain/cashflow/calculation.py`, `tests/unit/services/portfolio_transaction_processing_service/transaction/test_income_validation.py` |
| Dual cash-entry mode (AUTO_GENERATE vs UPSTREAM_PROVIDED) | COVERED | `src/services/portfolio_transaction_processing_service/app/domain/transaction/settlement/cash_entry.py`, `src/services/portfolio_transaction_processing_service/app/application/cashflow_processing/use_case.py`, `tests/unit/services/portfolio_transaction_processing_service/domain/transaction/settlement/test_cash_entry.py` |
| Withholding/net reconciliation primitives | COVERED | `src/services/portfolio_transaction_processing_service/app/domain/transaction/booked.py`, `src/services/portfolio_transaction_processing_service/app/domain/transaction/validation/income.py`, `tests/unit/services/portfolio_transaction_processing_service/transaction/test_income_validation.py` |
| Pre-fee net-interest and direction-aware settlement cash | COVERED | `src/services/portfolio_transaction_processing_service/app/domain/transaction/settlement/interest.py`, `tests/unit/services/portfolio_transaction_processing_service/domain/transaction/settlement/test_interest.py`, `tests/integration/services/portfolio_transaction_processing_service/test_int_combined_interest_processing.py` |
| Query/audit visibility via existing surfaces | COVERED | `query_service/app/dtos/transaction_dto.py`, `tests/integration/services/query_service/test_transactions_router.py`, `tests/unit/services/query_service/services/test_transaction_service.py` |
| DB propagation for INTEREST semantic fields | COVERED | `database_models.py`, `alembic/versions/d6e7f8a9b0c1_*.py`, persistence repository tests |
| Dedicated regression gate | COVERED | `scripts/quality/test_manifest.py`, `Makefile`, `.github/workflows/ci.yml` |

## Validation Evidence Executed

- `python -m pytest -q tests/unit/transaction_specs/test_interest_slice0_characterization.py`
- `python -m pytest -q tests/unit/services/portfolio_transaction_processing_service/transaction/test_income_validation.py`
- `python -m pytest -q tests/unit/services/portfolio_transaction_processing_service/domain/transaction/settlement/test_interest.py`
- `python -m pytest -q tests/unit/services/portfolio_transaction_processing_service/transaction/test_booking_metadata.py`
- `python -m pytest -q tests/unit/services/portfolio_transaction_processing_service/cost/test_cost_calculator.py -k "interest or dividend"`
- `python -m pytest -q tests/unit/services/portfolio_transaction_processing_service/application/cost_basis_processing/test_execution.py`
- `python -m pytest -q tests/unit/services/portfolio_transaction_processing_service/domain/transaction/settlement/test_cash_entry.py tests/unit/services/portfolio_transaction_processing_service/application/cashflow_processing/test_use_case.py`
- `python -m pytest -q tests/unit/services/portfolio_transaction_processing_service/domain/cashflow/test_calculation.py -k "interest"`
- `python -m pytest -q tests/unit/services/ingestion_service/test_transaction_model.py`
- `python -m pytest -q tests/unit/services/query_service/services/test_transaction_service.py`
- `python -m pytest -q tests/integration/services/query_service/test_transactions_router.py`
- `python -m pytest -q tests/integration/services/portfolio_transaction_processing_service/test_int_combined_interest_processing.py`
- `python scripts/quality/test_manifest.py --suite transaction-interest-contract --quiet`
- `python scripts/quality/migration_contract_check.py --mode alembic-sql`
- `python -m ruff check ... --ignore E501` on changed INTEREST slice files

## Residual Items

- One open product decision remains: whether withholding and other deductions should remain additive fields or move behind policy feature flags in a later refinement RFC.

