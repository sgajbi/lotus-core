# BUY Slice 6 - RFC Conformance Gate Report

## Scope

This report closes RFC-059 Slice 6 by mapping `RFC-BUY-01` requirements to implementation evidence and the dedicated BUY regression suite (`buy-rfc`).

Status labels:

- `COVERED`
- `PARTIALLY_COVERED`
- `NOT_COVERED`

Behavior labels:

- `MATCHES`
- `PARTIALLY_MATCHES`
- `DOES_NOT_MATCH`

## Section-Level Conformance Matrix

| RFC-BUY-01 Section | Status | Behavior | Evidence | Notes |
|---|---|---|---|---|
| 4. BUY Semantic Invariants | COVERED | MATCHES | `tests/unit/services/calculators/cost_calculator_service/engine/test_cost_calculator.py`, `tests/unit/transaction_specs/test_buy_slice0_characterization.py` | BUY quantity/cost progression and explicit zero realized P&L locked in tests. |
| 5. BUY Processing Flow | PARTIALLY_COVERED | PARTIALLY_MATCHES | `src/services/calculators/cost_calculator_service/app/consumer.py`, `tests/unit/services/calculators/cashflow_calculator_service/unit/core/test_cashflow_logic.py` | Lifecycle is implemented across ingestion/persistence/calculation/query with stage telemetry; a single persisted lifecycle-stage state machine is not yet implemented. |
| 6. BUY Canonical Data Model | COVERED | MATCHES | `tests/unit/services/ingestion_service/test_transaction_model.py`, `tests/unit/libs/portfolio_common/test_transaction_metadata_contract.py` | Canonical BUY metadata, linkage fields, and policy metadata are preserved end-to-end. |
| 7. BUY Validation Rules | COVERED | MATCHES | `tests/unit/libs/portfolio_common/test_buy_validation.py`, `docs/rfc-transaction-specs/transactions/BUY/BUY-SLICE-1-VALIDATION-REASON-CODES.md` | Deterministic reason codes and strict metadata validation are implemented. |
| 8. BUY Calculation Rules and Formulas | COVERED | MATCHES | `tests/unit/services/calculators/cost_calculator_service/engine/test_cost_calculator.py` | Calculation invariants and cross-currency rules are enforced. |
| 9. BUY Position Rules | COVERED | MATCHES | `tests/unit/transaction_specs/test_buy_slice0_characterization.py` | BUY increases position quantity and cost basis as required. |
| 10. BUY Lot Rules | COVERED | MATCHES | `tests/integration/services/calculators/cost_calculator_service/test_int_cost_repository_lot_offset.py` | Durable BUY lot-state creation/upsert behavior validated. |
| 11. BUY Cash and Dual-Accounting Rules | COVERED | MATCHES | `tests/unit/services/calculators/cashflow_calculator_service/unit/core/test_cashflow_logic.py`, `tests/unit/services/calculators/cost_calculator_service/engine/test_cost_calculator.py` | BUY outflow sign, linkage propagation, and dual-currency handling validated. |
| 12. BUY Accrued-Interest Offset Rules | COVERED | MATCHES | `tests/integration/services/calculators/cost_calculator_service/test_int_cost_repository_lot_offset.py` | Accrued-interest offset initialization and persistence are validated. |
| 13. BUY Timing Rules | PARTIALLY_COVERED | PARTIALLY_MATCHES | `tests/unit/libs/portfolio_common/test_buy_validation.py` | Date ordering and settlement-date requirements are enforced; broader policy-level timing modes remain to be added with later transaction RFC rollout. |
| 14. BUY Query / Output Contract | COVERED | MATCHES | `tests/unit/services/query_service/repositories/test_buy_state_repository.py`, `tests/unit/services/query_service/services/test_buy_state_service.py`, `tests/integration/services/query_service/test_buy_state_router.py` | BUY lot/offset/cash-linkage query surfaces are implemented and tested. |
| 17. BUY Test Matrix | COVERED | MATCHES | `scripts/test_manifest.py` (`buy-rfc` suite) | Dedicated regression suite now aggregates BUY-critical tests across unit/integration layers. |
| 19. BUY Configurable Policies | COVERED | MATCHES | `tests/unit/services/calculators/cost_calculator_service/engine/test_cost_calculator.py` | BUY policy hook coverage exists for accrued-interest exclusion policy. |
| 20. BUY Gap Assessment Checklist | COVERED | MATCHES | `docs/rfc-transaction-specs/transactions/BUY/BUY-SLICE-0-GAP-ASSESSMENT.md`, this report | Gap tracking and final conformance evidence are now both in-repo artifacts. |

## Dedicated Regression Suite

- Suite name: `buy-rfc`
- Source: `scripts/test_manifest.py`
- Local command: `make test-buy-rfc`
- CI command: `python scripts/test_manifest.py --suite buy-rfc --with-coverage --coverage-file .coverage.buy-rfc`
- CI wiring: `.github/workflows/ci.yml` test matrix includes `buy-rfc`

## Residual Accepted Gaps

1. Lifecycle stage persistence model:
   - Current state: stage-level metrics/logging exists, but no single persisted state-machine record per transaction.
   - Impact: low for current BUY correctness; medium for support diagnostics depth.
   - Disposition: accepted for BUY completion; can be elevated in a future observability-focused RFC.
2. Extended timing-policy modes:
   - Current state: mandatory date validation and ordering enforcement exists; advanced timing-mode expansion is not yet modeled as policy catalog.
   - Impact: low for current BUY baseline; future enhancement for broader policy programmability.
   - Disposition: accepted and explicitly tracked for follow-on transaction RFC work.

## Exit Decision

Slice 6 is complete for BUY under RFC-059:

- blocking BUY behaviors are covered and test-backed
- dedicated regression suite is wired into CI
- residual non-blocking gaps are explicit and accepted
