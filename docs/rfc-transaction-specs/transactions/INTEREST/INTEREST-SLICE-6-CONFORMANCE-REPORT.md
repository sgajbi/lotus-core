# INTEREST Slice 6 - Conformance Report

## Scope

This report closes RFC-070 execution by mapping `RFC-INTEREST-01` requirements to implementation evidence and suite wiring.

## Suite and CI Wiring

Delivered:

- `scripts/test_manifest.py`
  - `transaction-interest-contract`
  - alias `interest-rfc`
- `Makefile`
  - `test-transaction-interest-contract`
  - `test-interest-rfc`
- `.github/workflows/ci.yml`
  - matrix includes `transaction-interest-contract`

## Requirement-to-Evidence Mapping

| RFC Requirement Area | Status | Evidence |
| --- | --- | --- |
| Canonical INTEREST validation taxonomy | COVERED | `src/libs/portfolio-common/portfolio_common/transaction_domain/interest_reason_codes.py`, `interest_validation.py`, `tests/unit/libs/portfolio_common/test_interest_validation.py` |
| Strict metadata validation | COVERED | `validate_interest_transaction(..., strict_metadata=True)`, `tests/unit/libs/portfolio_common/test_interest_validation.py` |
| Deterministic linkage/policy enrichment | COVERED | `interest_linkage.py`, `src/services/calculators/cost_calculator_service/app/consumer.py`, `tests/unit/libs/portfolio_common/test_interest_linkage.py` |
| Calculation invariants (no qty/lot impact, explicit zero realized P&L) | COVERED | `src/services/calculators/cost_calculator_service/app/cost_engine/processing/cost_calculator.py` (`InterestStrategy`), `tests/unit/services/calculators/cost_calculator_service/engine/test_cost_calculator.py` |
| Direction semantics (income vs expense baseline) | COVERED | `interest_models.py`, `interest_validation.py`, `cashflow_logic.py`, tests in `test_interest_validation.py` and `test_cashflow_logic.py` |
| Dual cash-entry mode (AUTO_GENERATE vs UPSTREAM_PROVIDED) | COVERED | `cashflow transaction_consumer.py`, tests in `test_cashflow_transaction_consumer.py` |
| Withholding/net reconciliation primitives | COVERED | `interest_models.py`, `interest_validation.py`, `test_interest_validation.py` |
| Query/audit visibility via existing surfaces | COVERED | `query_service/app/dtos/transaction_dto.py`, `tests/integration/services/query_service/test_transactions_router.py`, `tests/unit/services/query_service/services/test_transaction_service.py` |
| DB propagation for INTEREST semantic fields | COVERED | `database_models.py`, `alembic/versions/d6e7f8a9b0c1_*.py`, persistence repository tests |
| Dedicated regression gate | COVERED | `scripts/test_manifest.py`, `Makefile`, `.github/workflows/ci.yml` |

## Validation Evidence Executed

- `python -m pytest -q tests/unit/transaction_specs/test_interest_slice0_characterization.py`
- `python -m pytest -q tests/unit/libs/portfolio_common/test_interest_validation.py`
- `python -m pytest -q tests/unit/libs/portfolio_common/test_interest_linkage.py`
- `python -m pytest -q tests/unit/services/calculators/cost_calculator_service/engine/test_cost_calculator.py -k "interest or dividend"`
- `python -m pytest -q tests/unit/services/calculators/cost_calculator_service/consumer/test_cost_calculator_consumer.py -k "interest_metadata_defaults"`
- `python -m pytest -q tests/unit/services/calculators/cashflow_calculator_service/unit/consumers/test_cashflow_transaction_consumer.py -k "interest_external_mode or dividend_external_mode"`
- `python -m pytest -q tests/unit/services/calculators/cashflow_calculator_service/unit/core/test_cashflow_logic.py -k "interest"`
- `python -m pytest -q tests/unit/services/ingestion_service/test_transaction_model.py`
- `python -m pytest -q tests/unit/services/query_service/services/test_transaction_service.py`
- `python -m pytest -q tests/integration/services/query_service/test_transactions_router.py`
- `python scripts/test_manifest.py --suite interest-rfc --quiet`
- `python scripts/migration_contract_check.py --mode alembic-sql`
- `python -m ruff check ... --ignore E501` on changed INTEREST slice files

## Residual Items

- One open product decision remains: whether withholding and other deductions should remain additive fields or move behind policy feature flags in a later refinement RFC.

