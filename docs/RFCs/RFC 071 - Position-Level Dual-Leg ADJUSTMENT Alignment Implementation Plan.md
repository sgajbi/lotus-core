# RFC 071 - Position-Level Dual-Leg ADJUSTMENT Alignment Implementation Plan

| Field | Value |
| --- | --- |
| Status | Implemented |
| Created | 2026-03-05 |
| Last Updated | 2026-03-07 |
| Owners | lotus-core engineering |
| Depends On | `docs/rfc-transaction-specs/transactions/RFC-POSITION-DUAL-LEG-ALIGNMENT-01.md`; `docs/rfc-transaction-specs/shared/13-dual-leg-accounting-and-cash-adjustment-model.md`; `docs/rfc-transaction-specs/shared/12-canonical-modeling-guidelines.md` |
| Related Standards | RFC-0067 OpenAPI/vocabulary governance; shared transaction lifecycle standards |
| Scope | In repo |

## Executive Summary
This RFC defines the implementation plan to enforce a strict dual-leg model in lotus-core for any transaction type that has both product semantics and cash impact. The product leg keeps business semantics, and the linked `ADJUSTMENT` cash leg is the authoritative cash-movement representation.

Implementation is completed in lotus-core with migrations, runtime dual-leg orchestration, and calculator alignment.

## Implementation Closure (2026-03-05)
Delivered:
1. Canonical dual-leg metadata contract completed across ingestion DTOs, event model, query DTOs, and persistence schema:
 - `settlement_cash_account_id`, `settlement_cash_instrument_id`
 - `movement_direction`
 - `originating_transaction_id`, `originating_transaction_type`
 - `adjustment_reason`, `link_type`, `reconciliation_key`
2. `AUTO_GENERATE` enforcement and generation:
 - shared adjustment cash-leg builder implemented
 - cost calculator consumer generates, persists, links, and emits `ADJUSTMENT` cash legs
3. `UPSTREAM_PROVIDED` pairing gate:
 - portfolio-scoped lookup by `external_cash_transaction_id`
 - quality-gated pairing via shared dual-leg validator before product-leg downstream handoff
4. Calculator source-of-truth alignment:
 - `ADJUSTMENT` support added in financial calculator transaction enum/strategy map
 - cashflow consumer skips product-leg cashflow when a linked cash leg exists
 - cashflow logic uses `movement_direction` for `ADJUSTMENT` sign
 - position calculator applies signed quantity/cost updates for `ADJUSTMENT`
5. Cashflow rule coverage:
 - migration adds canonical `ADJUSTMENT` cashflow rule (`TRANSFER`, `EOD`, position-flow only)
6. Tests:
 - new unit suites for adjustment cash-leg builder and dual-leg behaviors
 - updated cost/cashflow/position tests for auto-generation, pairing, and no-double-count behavior

Validation evidence:
1. `pytest` targeted unit suites:
 - `tests/unit/libs/portfolio_common/test_adjustment_cash_leg.py`
 - `tests/unit/services/calculators/cost_calculator_service/consumer/test_cost_calculator_consumer.py`
 - `tests/unit/services/calculators/cashflow_calculator_service/unit/core/test_cashflow_logic.py`
 - `tests/unit/services/calculators/cashflow_calculator_service/unit/consumers/test_cashflow_transaction_consumer.py`
 - `tests/unit/services/calculators/position_calculator/core/test_position_logic.py`
 - `tests/unit/libs/portfolio_common/test_dividend_validation.py`
 - `tests/unit/libs/portfolio_common/test_interest_validation.py`
2. Migration contract gate:
 - `python scripts/migration_contract_check.py --mode alembic-sql`

Residual operational note:
1. Local persistence integration test environment may require migration refresh to latest head before executing full integration repository suites, due existing local DB schema drift.

## Goals
1. Enforce one canonical cross-transaction model for all events with product + cash impact.
2. Eliminate cash double counting across calculators and reporting paths.
3. Support both canonical cash-entry modes:
 - `AUTO_GENERATE` (engine generates cash leg)
 - `UPSTREAM_PROVIDED` (upstream provides cash leg and linkage)
4. Keep implementation modular and reusable across all four transaction types.
5. Reuse existing APIs and query surfaces; no dedicated transaction-type endpoints.

## Non-Goals
1. No new standalone endpoint family for this change.
2. No redesign of portfolio-level cash-native transaction semantics (`DEPOSIT`, `WITHDRAWAL`, cash-only transfers).
3. No replacement of existing transaction IDs or replay strategy.

## Canonical Naming and Attribute Decisions
1. Cash leg transaction type: `ADJUSTMENT`.
2. `cash_entry_mode` values are canonicalized to: `AUTO_GENERATE` and `UPSTREAM_PROVIDED`.
3. No alias behavior is introduced in code for cash-entry mode values.
4. Required linkage metadata across paired legs:
 - `economic_event_id`
 - `linked_transaction_group_id`
 - `originating_transaction_id`
 - `originating_transaction_type`
 - `link_type`
 - `reconciliation_key` (when available)
5. External cash linkage key remains `external_cash_transaction_id` and is mandatory when `cash_entry_mode = UPSTREAM_PROVIDED`.
6. Cash movement source-of-truth for downstream balance/performance: linked `ADJUSTMENT` leg.

## Current Baseline (as-is)
1. BUY/SELL already have stronger linkage patterns and slice artifacts.
2. DIVIDEND/INTEREST now support metadata enrichment and external cash-entry mode behavior.
3. Runtime metadata fields (`economic_event_id`, `linked_transaction_group_id`, `cash_entry_mode`, `external_cash_transaction_id`) exist in ingestion DTOs, event model, and persistence model.
4. Cross-transaction dual-leg source-of-truth policy is not yet codified end-to-end as one enforced standard across calculators.

## Generic Applicability Rule
1. The dual-leg pattern is not limited to `BUY`, `SELL`, `DIVIDEND`, or `INTEREST`.
2. Any current or future transaction type with product semantics and cash impact must use the same product-leg + `ADJUSTMENT` cash-leg model.
3. The architecture must use shared, transaction-agnostic linkage and validation components, with transaction-type-specific extensions only where economically required.

## Pairing and Linkage Architecture Requirements
1. For `cash_entry_mode = AUTO_GENERATE`, the engine must generate the `ADJUSTMENT` cash leg immediately and link it to the product leg before publishing to downstream calculators.
2. For `cash_entry_mode = UPSTREAM_PROVIDED`, the system must locate the corresponding upstream cash transaction for the same `portfolio_id` and pairing keys, then validate and link it before downstream calculator processing.
3. Upstream-provided cash legs must pass quality checks before acceptance:
 - required linkage identifiers are present and consistent
 - transaction type is `ADJUSTMENT`
 - amount/direction reconcile to product-leg economic expectations within configured tolerance
 - no duplicate cash leg is already linked for the same economic event
4. If quality checks fail, the pair must be rejected or parked according to policy; partial downstream processing is not allowed.
5. Linking ownership rule:
 - upstream-provided mode: upstream owns creation of both legs and linkage consistency
 - auto-generate mode: engine owns creation of cash leg and linkage consistency
6. After successful linkage, downstream calculators must process both modes identically and must not branch logic based on leg origin.
7. Downstream processing contract is mode-agnostic:
 - calculators consume `ADJUSTMENT` as standard cash-leg transaction type
 - calculators do not rely on whether cash leg was generated internally or supplied upstream

## Gap Matrix
| Requirement | Current State | Gap | Planned Slice |
| --- | --- | --- | --- |
| Cross-transaction dual-leg canonical contract | Partially implemented | Behavior exists in parts but not standardized as one enforceable contract | Slice 1 |
| Canonical cash-entry mode naming | Partially implemented | Mixed mode naming is present across docs and code paths | Slice 1-2 |
| Generic future transaction-type extensibility | Partially implemented | Current pattern is documented mostly around four transaction types | Slice 2 |
| Portfolio-scoped upstream cash-leg discovery and quality gating | Partially implemented | External cash references exist but no single standardized pairing contract | Slice 3 |
| ADJUSTMENT metadata completeness | Partially implemented | Not all code paths guarantee full origin/reason/link metadata consistently | Slice 3-4 |
| No-double-count enforcement in calculators | Partially implemented | Guardrails are not uniformly explicit across all flows | Slice 4 |
| Query/read-model visibility of dual-leg linkage | Partially implemented | Existing transaction surfaces need explicit dual-leg evidence fields and tests | Slice 5 |
| End-to-end conformance evidence | Not implemented | No unified dual-leg conformance suite/report | Slice 6 |

## Slice Plan

### Slice 0 - Baseline and Characterization (No behavior change)
Deliverables:
1. Characterization matrix for current BUY/SELL/DIVIDEND/INTEREST dual-leg behavior.
2. Explicit list of preserved vs changed behavior.

Exit Criteria:
1. Baseline is locked by tests and referenced in this RFC.

### Slice 1 - Shared Spec and Naming Normalization
Deliverables:
1. Normalize shared/spec docs to one canonical cash-entry-mode vocabulary: `AUTO_GENERATE` and `UPSTREAM_PROVIDED`.
2. Remove mixed terminology and document explicit non-alias policy.
3. Add/refresh transaction-doc index references for shared doc `13` and dual-leg change RFC.

Exit Criteria:
1. No naming ambiguity remains between docs and runtime fields.

### Slice 2 - Generic Domain Model and Validation Hardening
Deliverables:
1. Reusable transaction-agnostic dual-leg validation utilities for product leg + `ADJUSTMENT` leg linkage checks.
2. Mandatory reason-code coverage for missing/mismatched/duplicate cash-leg scenarios.
3. Standardized metadata population rules for `originating_transaction_type` and `adjustment_reason`.
4. Extension hooks so future transaction types can adopt dual-leg behavior without duplicating pairing logic.

Exit Criteria:
1. Validation semantics are deterministic and reusable across current and future dual-leg transaction types.

### Slice 3 - Portfolio-Scoped Pairing, Persistence, and Event Contract Completion
Deliverables:
1. Standardized pairing workflow for `UPSTREAM_PROVIDED` mode using `portfolio_id` + linkage keys.
2. Enforce quality-gated acceptance of upstream cash leg before downstream calculator handoff.
3. Ensure required dual-leg metadata is persisted and replay-safe.
4. Add migrations only if required by uncovered metadata gaps.
5. Contract tests for persistence round-trip and idempotent replay.

Exit Criteria:
1. Product/cash-leg linkage survives full ingestion->calculator->persistence flow for both modes.
2. Upstream-provided cash-leg pairing is deterministic and auditable.

### Slice 4 - Calculator Source-of-Truth and No-Double-Count Enforcement
Deliverables:
1. Enforce that cash mutation and performance cashflow source from linked `ADJUSTMENT` leg when present.
2. Product leg cash fields remain reconciliation/explainability-only when linked cash exists.
3. Add explicit negative tests for double counting.
4. Remove mode-specific calculator branching that depends on leg origin after linkage is complete.

Exit Criteria:
1. Cashflow and performance invariants are deterministic and test-enforced.
2. Calculators process both modes identically once linkage is valid.

### Slice 5 - Query/Observability Alignment (No dedicated endpoints)
Deliverables:
1. Extend existing transaction/supportability responses to show dual-leg linkage evidence.
2. OpenAPI and vocabulary updates only on existing endpoints.
3. Operator-facing diagnostics for mode (`AUTO_GENERATE`/`UPSTREAM_PROVIDED`) and linkage status.

Exit Criteria:
1. Existing query surfaces can explain dual-leg state without custom endpoint families.

### Slice 6 - Conformance Suite, CI Wiring, and Exit Report
Deliverables:
1. Dedicated dual-leg contract suite in test manifest and Makefile targets.
2. CI lane integration.
3. Conformance report mapping this RFC + source specs to implementation evidence.

Exit Criteria:
1. Dual-leg standard has an explicit regression gate and closure artifact.

## Architecture Guardrails
1. Reusable components first: shared validators, shared metadata enrichers, shared linkage checks.
2. No duplicated transaction-specific logic for the same dual-leg rule.
3. Additive changes only; no breaking behavior removal without explicit approval.
4. Deterministic replay/idempotency behavior must be preserved.

## Test Strategy
Per approved slice, run applicable gates:
1. `python -m ruff check ...`
2. `make typecheck`
3. targeted unit/integration/e2e suites
4. `python scripts/migration_contract_check.py --mode alembic-sql` (if migration touched)
5. `python scripts/openapi_quality_gate.py` (if API touched)
6. `python scripts/api_vocabulary_inventory.py --output docs/standards/api-vocabulary/lotus-core-api-vocabulary.v1.json` (if API touched)
7. `python scripts/api_vocabulary_inventory.py --validate-only` (if API touched)

## Risks and Mitigations
1. Risk: hidden cash double counting through legacy assumptions.
 - Mitigation: explicit no-double-count tests across cashflow + performance paths.
2. Risk: mode mismatch between docs and runtime fields.
 - Mitigation: Slice 1 naming normalization and contract assertions.
3. Risk: incomplete metadata in external cash mode.
 - Mitigation: strict validation + persistence contract tests.

## Approval Required
Implementation must not begin until this RFC is approved.

Approval checklist:
1. Naming and attribute decisions accepted (`ADJUSTMENT`, `AUTO_GENERATE`/`UPSTREAM_PROVIDED`).
2. No-dedicated-endpoint direction accepted.
3. Slice boundaries and gates accepted.
4. Cross-calculator source-of-truth rule accepted.

## Merge Verification (2026-03-07)
1. RFC-071 implementation is merged on `main`.
2. Verified on commit `001e084b06f1da4ba955ce9de7ec5833a7a73181`.
3. PR evidence: `#191` (final forward-port coverage parity on latest main).
