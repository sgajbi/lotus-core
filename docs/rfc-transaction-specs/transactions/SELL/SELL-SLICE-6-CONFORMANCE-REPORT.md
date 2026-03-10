# SELL Slice 6 - RFC Conformance Gate Report

## Scope

This report closes RFC-061 Slice 6 by mapping `RFC-SELL-01` requirements to implementation evidence and the dedicated SELL regression suite (`sell-rfc`).

Status labels:

- `COVERED`
- `PARTIALLY_COVERED`
- `NOT_COVERED`

Behavior labels:

- `MATCHES`
- `PARTIALLY_MATCHES`
- `DOES_NOT_MATCH`

## Section-Level Conformance Matrix

| RFC-SELL-01 Section | Status | Behavior | Evidence | Notes |
|---|---|---|---|---|
| 4. SELL Semantic Invariants | COVERED | MATCHES | `tests/unit/services/calculators/cost_calculator_service/engine/test_cost_calculator.py`, `tests/unit/transaction_specs/test_sell_slice0_characterization.py` | SELL proceeds, consumed quantity, and disposal sign invariants are test-enforced. |
| 5. SELL Processing Flow | PARTIALLY_COVERED | PARTIALLY_MATCHES | `src/services/calculators/cost_calculator_service/app/consumer.py`, `tests/unit/services/calculators/cost_calculator_service/consumer/test_cost_calculator_consumer.py` | Lifecycle orchestration and stage telemetry are implemented; a single persisted lifecycle state machine is not yet modeled. |
| 6. SELL Canonical Data Model | COVERED | MATCHES | `tests/unit/services/ingestion_service/test_transaction_model.py`, `tests/unit/libs/portfolio_common/test_sell_linkage.py` | Canonical SELL metadata, linkage fields, and policy metadata are preserved end-to-end. |
| 7. SELL Validation Rules | COVERED | MATCHES | `tests/unit/libs/portfolio_common/test_sell_validation.py`, `docs/rfc-transaction-specs/transactions/SELL/SELL-SLICE-1-VALIDATION-REASON-CODES.md` | Deterministic SELL reason codes and strict validation implemented. |
| 8. SELL Calculation Rules and Formulas | COVERED | MATCHES | `tests/unit/services/calculators/cost_calculator_service/engine/test_cost_calculator.py` | Realized P&L and proceeds/cost basis invariants enforced with deterministic error semantics. |
| 9. SELL Position Rules | COVERED | MATCHES | `tests/unit/transaction_specs/test_sell_slice0_characterization.py` | SELL decreases position quantity and cost basis as required. |
| 10. SELL Disposal Rules | PARTIALLY_COVERED | PARTIALLY_MATCHES | `src/services/calculators/cost_calculator_service/app/cost_engine/processing/cost_calculator.py`, `tests/unit/services/calculators/cost_calculator_service/engine/test_cost_calculator.py` | Deterministic disposal and oversell gates are implemented; dedicated persisted per-lot disposal rows are not modeled yet. |
| 11. SELL Cash and Dual-Accounting Rules | COVERED | MATCHES | `tests/unit/services/calculators/cashflow_calculator_service/unit/core/test_cashflow_logic.py`, `tests/unit/services/query_service/services/test_sell_state_service.py` | SELL inflow sign, linkage propagation, and cash reconciliation shape are validated. |
| 12. SELL Timing Rules | PARTIALLY_COVERED | PARTIALLY_MATCHES | `tests/unit/libs/portfolio_common/test_sell_validation.py` | Settlement date and date ordering rules are enforced; extended timing policy modes remain future work. |
| 14. SELL Query / Output Contract | COVERED | MATCHES | `tests/unit/services/query_service/repositories/test_sell_state_repository.py`, `tests/unit/services/query_service/services/test_sell_state_service.py`, `tests/integration/services/query_service/test_sell_state_router.py` | SELL disposal and cash-linkage query surfaces are implemented and tested. |
| 17. SELL Test Matrix | COVERED | MATCHES | `scripts/test_manifest.py` (`sell-rfc` suite) | Dedicated regression suite aggregates SELL-critical tests across unit/integration layers and CI matrix. |
| 19. SELL Configurable Policies | PARTIALLY_COVERED | PARTIALLY_MATCHES | `tests/unit/libs/portfolio_common/test_sell_linkage.py`, `tests/unit/services/calculators/cost_calculator_service/engine/test_cost_calculator.py` | FIFO/AVCO deterministic policy assignment implemented; oversold policy is explicit but unsupported by design. |
| 20. SELL Gap Assessment Checklist | COVERED | MATCHES | `docs/rfc-transaction-specs/transactions/SELL/SELL-SLICE-0-GAP-ASSESSMENT.md`, this report | Gap matrix plus final conformance evidence are both in-repo artifacts. |

## Dedicated Regression Suite

- Suite name: `sell-rfc`
- Source: `scripts/test_manifest.py`
- Local command: `make test-sell-rfc`
- CI command: `python scripts/test_manifest.py --suite sell-rfc --with-coverage --coverage-file .coverage.sell-rfc`
- CI wiring: `.github/workflows/ci.yml` test matrix includes `sell-rfc`

## Residual Accepted Gaps

1. Persisted lifecycle stage state model:
   - Current state: stage-level metrics/logging exists, but no persisted single state-machine row per transaction.
   - Impact: low for current SELL correctness; medium for support diagnostics depth.
   - Disposition: accepted for SELL completion and tracked for follow-on observability RFC work.

2. Per-lot disposal persistence model:
   - Current state: disposal effects are deterministic at calculation time and exposed via transaction-level query state; discrete persisted lot-disposal rows are not yet implemented.
   - Impact: medium for forensic lot-level replay detail.
   - Disposition: accepted for current SELL baseline; can be addressed in a targeted disposal-state RFC.

3. Oversold policy mode enablement:
   - Current state: strict oversell reject is enforced; oversold policy option is explicit and fails as unsupported.
   - Impact: low for current baseline policy.
   - Disposition: accepted until short-selling policy model is introduced.

## Exit Decision

Slice 6 is complete for SELL under RFC-061:

- blocking SELL behaviors are covered and test-backed
- dedicated regression suite is wired into CI
- residual non-blocking gaps are explicit and accepted
