# DIVIDEND Slice 6 - Conformance Report

## Scope
This report maps RFC-DIVIDEND-01 requirements to implementation evidence delivered through slices 0..6.

## Conformance Summary
| RFC Area | Status | Evidence |
| --- | --- | --- |
| Section 4 semantic invariants (no qty change, no lot effects, no realized P&L) | Covered | `DividendStrategy` invariants and tests in cost calculator + slice 3 doc |
| Section 4 linkage invariants (`economic_event_id`, linkage group) | Covered | DIVIDEND metadata enrichment + persistence/query propagation + tests |
| Section 5 processing flow (validate -> enrich -> policy metadata -> calculate -> persist/publish) | Covered | DIVIDEND domain validation/linkage modules + cost/cashflow consumer integrations |
| Section 8 explicit zero realized P&L fields | Covered | DIVIDEND cost strategy sets realized fields to explicit zero and tests |
| Section 10 dual cash-entry mode | Covered (naming normalization) | `AUTO_GENERATE`/`UPSTREAM_PROVIDED` mode support, external-link enforcement, skip-auto-cashflow path |
| Section 13 query/output visibility over existing surfaces | Covered | transaction query DTO exposes mode/linkage fields; router/service tests |
| Section 16 required test matrix (validation/calc/cash/query/idempotency) | Partially Covered | dedicated `transaction-dividend-contract` suite + targeted unit/integration tests |
| Section 11 withholding-tax decomposition | Partially Covered | gross amount and cash linkage handled; dedicated withholding decomposition pending |
| Section 11 return-of-capital separation and basis reduction | Not Covered | ROC decomposition and basis-reduction policy path pending |
| Section 12 advanced timing dimensions (`EX_DATE`, `RECORD_DATE`, etc.) | Not Covered | current implementation remains transaction/settlement-date centric |

## Suite and CI Wiring Evidence
1. Added `transaction-dividend-contract` suite in `scripts/test_manifest.py`.
2. Added backward-compatible alias `transaction-dividend-contract` in `scripts/test_manifest.py`.
3. Added `Makefile` targets:
 - `test-transaction-dividend-contract`
 - `test-transaction-dividend-contract`
4. Added CI matrix execution in `.github/workflows/ci.yml`:
 - `suite: transaction-dividend-contract`

## Validations Executed for Slice 6
1. `python scripts/test_manifest.py --suite transaction-dividend-contract --validate-only`
2. `python -m pytest -q tests/unit/transaction_specs/test_dividend_slice0_characterization.py tests/unit/libs/portfolio_common/test_dividend_validation.py tests/unit/libs/portfolio_common/test_dividend_linkage.py tests/unit/libs/portfolio_common/test_cash_entry_mode.py tests/unit/services/calculators/cashflow_calculator_service/unit/consumers/test_cashflow_transaction_consumer.py tests/integration/services/query_service/test_transactions_router.py`
3. `python -m ruff check scripts/test_manifest.py tests/unit/transaction_specs/test_dividend_slice0_characterization.py tests/unit/libs/portfolio_common/test_dividend_validation.py tests/unit/libs/portfolio_common/test_dividend_linkage.py tests/unit/libs/portfolio_common/test_cash_entry_mode.py tests/unit/services/calculators/cashflow_calculator_service/unit/consumers/test_cashflow_transaction_consumer.py tests/integration/services/query_service/test_transactions_router.py --ignore E501`

## Residual Gaps (Explicit)
1. Withholding-tax canonical decomposition fields and reconciliation identities are not yet implemented end-to-end.
2. Return-of-capital decomposition and cost-basis-reduction policy behavior are not yet implemented.
3. Advanced timing policy dimensions (`EX_DATE`/`RECORD_DATE`/`PAYMENT_DATE` separation) are not yet implemented.
4. Late-link reconciliation SLA workflows for external cash-link arrival are only partially represented.

## Closure Statement
Slice 6 deliverables (suite wiring, alias, CI inclusion, conformance reporting) are complete.
Full RFC-DIVIDEND-01 closure still requires follow-on delivery for withholding/ROC/timing gaps listed above.

