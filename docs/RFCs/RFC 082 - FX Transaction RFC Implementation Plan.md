# RFC 082 - FX Transaction RFC Implementation Plan

| Field | Value |
| --- | --- |
| Status | Implemented |
| Created | 2026-03-09 |
| Last Updated | 2026-03-09 |
| Owners | lotus-core engineering |
| Depends On | `docs/rfc-transaction-specs/transactions/FX/RFC-FX-01 Canonical FX Transaction Specification.md`; shared transaction lifecycle specs |
| Related Standards | RFC-0067 OpenAPI/vocabulary governance; RFC-065 service/runtime standards; durability/consistency, rounding, and migration-contract standards |
| Scope | In repo |

## Executive Summary
This RFC defines the implementation plan for canonical FX processing in `lotus-core`, covering `FX_SPOT`, `FX_FORWARD`, and `FX_SWAP` as a single coordinated delivery. FX is not a minor extension of BUY/SELL or the existing dual-leg `ADJUSTMENT` pattern. It is a distinct domain that requires:
1. a cash-settlement layer with two FX-classified cash-native legs;
2. a contract-exposure layer for forwards and swaps, and optional spot exposure under policy;
3. deterministic linkage across economic event, component set, swap leg grouping, and contract lifecycle;
4. explicit realized P&L semantics where realized capital P&L is zero and realized FX P&L is first-class;
5. downstream calculator/query support that remains auditable and replay-safe.

Current `lotus-core` already has strong FX-rate infrastructure for valuation and reporting, but it does not yet implement canonical FX transactions. There are no FX transaction types in the engine enum, no FX contract instrument lifecycle, no FX-specific validation/linkage domain models, and no dedicated conformance suite. This plan closes those gaps incrementally while preserving the current architecture and avoiding incorrect reuse of the generic `ADJUSTMENT` cash-leg model.

## Original Requested Requirements (Preserved)
1. Implement `RFC-FX-01` semantics for `FX_SPOT`, `FX_FORWARD`, and `FX_SWAP` in one coherent model rather than fragmented transaction-specific shortcuts.
2. Treat FX cash settlement legs as FX-native components, not generic `ADJUSTMENT` cash legs.
3. Introduce canonical FX processing components:
 - `FX_CONTRACT_OPEN`
 - `FX_CONTRACT_CLOSE`
 - `FX_CASH_SETTLEMENT_BUY`
 - `FX_CASH_SETTLEMENT_SELL`
4. Support deterministic linkage across all FX components using `economic_event_id`, `linked_transaction_group_id`, `component_type`, `component_id`, `linked_component_ids`, and contract/swap identifiers.
5. Introduce `FX_CONTRACT` exposure modeling for forwards and swaps, with optional spot exposure controlled by policy.
6. Implement explicit realized P&L semantics:
 - `realized_capital_pnl_local = 0`
 - `realized_fx_pnl_local` is explicit and auditable
 - `realized_total_pnl_local = realized_fx_pnl_local`
7. Support spot, forward, and swap lifecycle timing semantics without losing replay safety or reconciliation quality.
8. Extend query/observability surfaces and test gates so FX can be operated and audited to the same standard as other canonical transaction families.

## Current Implementation Reality (Baseline)
1. `TransactionType` in `src/services/calculators/cost_calculator_service/app/cost_engine/domain/enums/transaction_type.py` does not include `FX_SPOT`, `FX_FORWARD`, `FX_SWAP`, or the FX component transaction types defined by `RFC-FX-01`.
2. The cost engine has canonical BUY/SELL/DIVIDEND/INTEREST/portfolio-flow routing, but no FX-specific strategy, no FX contract handling, and no realized-FX-P&L-specific transaction path.
3. The existing dual-leg accounting helpers under `portfolio_common.transaction_domain.adjustment_cash_leg` explicitly serve `DIVIDEND` and `INTEREST` via `ADJUSTMENT`; that model is not correct for FX because both settlement legs remain FX-classified cash components.
4. Position and cashflow calculators have no canonical notion of `FX_CONTRACT` instruments, `FX_CONTRACT_OPEN`/`FX_CONTRACT_CLOSE`, or near/far swap leg grouping.
5. Ingestion and query DTOs currently expose rich adjustment/dividend/interest metadata, but no FX-specific contract identifiers, cash-leg roles, quote conventions, swap grouping ids, or realized FX policy metadata.
6. `lotus-core` already supports FX rate ingestion, FX query, and cross-currency conversion for valuation/timeseries/reporting. That infrastructure is reusable, but it is not transaction-domain FX processing.
7. No dedicated characterization, unit, integration, or E2E conformance suite exists today for canonical FX behavior.

## Requirement-to-Implementation Gap Matrix
| Requirement | Current State | Gap | Planned Slice |
| --- | --- | --- | --- |
| Canonical FX business transaction types and processing component taxonomy | Not implemented | No FX transaction types or component typing in engine/domain model | Slice 1 |
| FX validation reason codes and strict canonical contract | Not implemented | No `fx_models`, `fx_reason_codes`, or `fx_validation` modules | Slice 1 |
| Deterministic component/linkage persistence | Not implemented | No stable FX component/linkage metadata model across persistence/query | Slice 2 |
| FX cash settlement layer | Not implemented | No FX-native settlement leg generation/acceptance/classification | Slice 3 |
| FX contract instrument and lifecycle | Not implemented | No `FX_CONTRACT` instrument or open/close lifecycle handling | Slice 4 |
| Swap near/far leg grouping semantics | Not implemented | No `swap_event_id`, `near_leg_group_id`, or `far_leg_group_id` handling | Slice 5 |
| Realized FX P&L semantics and policy traceability | Not implemented | No FX-specific realized P&L contract or policy mode support | Slice 6 |
| Query/observability supportability | Not implemented | No FX-specific traceability on existing query/support surfaces | Slice 7 |
| Dedicated FX regression gate and conformance report | Implemented | `transaction-fx-contract` / `transaction-fx-contract` suite wiring, CI matrix entry, conformance report, and FX E2E lifecycle coverage | Slice 8 |

## Slice Plan (0..8)

## Slice Execution Status
| Slice | Status | Evidence |
| --- | --- | --- |
| 0 | Completed | `docs/rfc-transaction-specs/transactions/FX/FX-SLICE-0-GAP-ASSESSMENT.md`, `tests/unit/transaction_specs/test_fx_slice0_characterization.py` |
| 1 | Completed | `docs/rfc-transaction-specs/transactions/FX/FX-SLICE-1-VALIDATION-REASON-CODES.md`, `tests/unit/libs/portfolio_common/test_fx_validation.py`, `alembic/versions/ac23de45f678_feat_add_fx_transaction_metadata_fields.py` |
| 2 | Completed | `docs/rfc-transaction-specs/transactions/FX/FX-SLICE-2-PERSISTENCE-LINKAGE.md`, `tests/unit/libs/portfolio_common/test_fx_linkage.py`, `tests/integration/services/persistence_service/repositories/test_repositories.py` (code added; local runtime blocked without Docker), `alembic/versions/ac23de45f678_feat_add_fx_transaction_metadata_fields.py` |
| 3 | Completed | `alembic/versions/ad34ef56a789_feat_add_fx_cash_settlement_rules.py`, `tests/unit/services/calculators/cashflow_calculator_service/unit/core/test_cashflow_logic.py`, `tests/integration/services/calculators/cashflow_calculator_service/test_cashflow_rule_contract.py` |
| 4 | Completed | `docs/rfc-transaction-specs/transactions/FX/FX-SLICE-4-CONTRACT-LIFECYCLE.md`, `tests/unit/libs/portfolio_common/test_fx_contract_instrument.py`, `tests/unit/services/calculators/position_calculator/core/test_position_logic.py`, `tests/unit/services/calculators/cost_calculator_service/consumer/test_cost_calculator_consumer.py`, `alembic/versions/be45fa67b890_feat_add_fx_contract_instrument_fields.py` |
| 5 | Completed | `docs/rfc-transaction-specs/transactions/FX/FX-SLICE-5-SWAP-GROUPING.md`, `tests/unit/libs/portfolio_common/test_fx_linkage.py`, `tests/unit/libs/portfolio_common/test_fx_validation.py` |
| 6 | Completed | `docs/rfc-transaction-specs/transactions/FX/FX-SLICE-6-PNL-SEMANTICS.md`, `tests/unit/services/calculators/cost_calculator_service/consumer/test_cost_calculator_consumer.py`, `tests/unit/libs/portfolio_common/test_fx_validation.py` |
| 7 | Completed | `docs/rfc-transaction-specs/transactions/FX/FX-SLICE-7-QUERY-OBSERVABILITY.md`, `tests/unit/services/query_service/repositories/test_transaction_repository.py`, `tests/unit/services/query_service/services/test_transaction_service.py`, `scripts/openapi_quality_gate.py` |
| 8 | Completed | `docs/rfc-transaction-specs/transactions/FX/FX-SLICE-8-CONFORMANCE-REPORT.md`, `scripts/test_manifest.py`, `Makefile`, `.github/workflows/ci.yml`, `tests/e2e/test_fx_lifecycle.py`, live Docker-backed validation (`transaction-fx-contract`: 195 passed; `test_fx_lifecycle.py`: 3 passed) |

### Slice 0 - Gap Assessment and Characterization Baseline (docs + tests, no behavior change)
Deliverables:
1. `docs/rfc-transaction-specs/transactions/FX/FX-SLICE-0-GAP-ASSESSMENT.md`
2. Characterization tests capturing current behavior when FX-like records are absent/unsupported and documenting which invariants must change.
3. Explicit baseline note separating reusable infrastructure (FX rates, cross-currency valuation) from missing FX transaction-domain behavior.

Exit Criteria:
1. Current non-support for canonical FX transactions is documented precisely.
2. Baseline behavior is locked to prevent accidental semantic drift during implementation.

### Slice 1 - Canonical FX Validation, Vocabulary, and Reason Codes
Deliverables:
1. `portfolio_common.transaction_domain.fx_models`
2. `portfolio_common.transaction_domain.fx_reason_codes`
3. `portfolio_common.transaction_domain.fx_validation`
4. Canonical fields for:
 - business transaction type (`FX_SPOT`, `FX_FORWARD`, `FX_SWAP`)
 - `component_type`
 - `fx_cash_leg_role`
 - quote convention
 - contract identifiers
 - swap grouping identifiers
5. Unit tests mirroring canonical transaction-domain validator patterns.
6. `docs/rfc-transaction-specs/transactions/FX/FX-SLICE-1-VALIDATION-REASON-CODES.md`

Exit Criteria:
1. Deterministic FX reason-code taxonomy exists.
2. Strict canonical validation exists for the FX economic event and its component members.
3. No aliases are introduced; vocabulary remains canonical snake_case only.

### Slice 2 - Persistence, Metadata Enrichment, and Linkage Traceability
Deliverables:
1. Persistence model/extensions for FX component metadata and linkage identifiers.
2. Canonical enrichment helper for deterministic defaults when upstream linkage is partial but policy allows completion.
3. Query/persistence round-trip tests proving linkage survives ingestion -> persistence -> query.
4. Migration-contract evidence if schema changes are required.
5. `docs/rfc-transaction-specs/transactions/FX/FX-SLICE-2-PERSISTENCE-LINKAGE.md`

Exit Criteria:
1. Every FX component can be traced to its economic event and component group deterministically.
2. Contract and swap linkage survive replay and reprocessing without ambiguity.

### Slice 3 - FX Cash Settlement Layer
Deliverables:
1. Support for `FX_CASH_SETTLEMENT_BUY` and `FX_CASH_SETTLEMENT_SELL` as canonical FX-classified settlement components.
2. Calculator handling for two-cash-leg FX exchange semantics without collapsing into `ADJUSTMENT`.
3. Cashflow classification rules that keep FX settlement observable as FX-driven flows while remaining consistent with portfolio and cash-instrument reporting.
4. Support for related linked `FEE`/`TAX` postings when present.
5. `docs/rfc-transaction-specs/transactions/FX/FX-SLICE-3-CASH-SETTLEMENT.md`

Exit Criteria:
1. Settlement cash legs reconcile as a linked pair with opposite cash roles.
2. Both legs remain FX-classified and audit-friendly.
3. Existing ADJUSTMENT logic is not misapplied to FX.

### Slice 4 - FX Contract Instrument and Lifecycle
Deliverables:
1. Introduce `InstrumentType = FX_CONTRACT` where required by current architecture.
2. Support `FX_CONTRACT_OPEN` and `FX_CONTRACT_CLOSE` lifecycle records for forwards and swaps.
3. Spot exposure policy support with explicit baseline default `spot_exposure_model = NONE` unless policy says otherwise.
4. Position/calculation handling for contract exposure lifecycle from trade date to settlement/maturity.
5. `docs/rfc-transaction-specs/transactions/FX/FX-SLICE-4-CONTRACT-LIFECYCLE.md`

Exit Criteria:
1. Forwards and swaps produce deterministic contract exposure state.
2. Contract lifecycle is replay-safe and compatible with downstream valuation/timeseries handoff.
3. Spot exposure behavior is explicit and policy-driven, not implicit.

### Slice 5 - FX Swap Orchestration and Multi-Leg Grouping
Deliverables:
1. Canonical handling for `FX_SWAP` as two linked FX legs (near/far).
2. Support for `swap_event_id`, `near_leg_group_id`, and `far_leg_group_id` across all related components.
3. Deterministic ordering, linkage, and replay handling for near/far lifecycle processing.
4. Tests covering mixed settlement dates, partial upstream ordering, and replay/idempotency behavior.
5. `docs/rfc-transaction-specs/transactions/FX/FX-SLICE-5-SWAP-GROUPING.md`

Exit Criteria:
1. Near/far swap legs remain linked as one economic swap while preserving each leg's local lifecycle.
2. Reprocessing cannot break or duplicate swap grouping semantics.

### Slice 6 - Realized P&L, Policy Modes, and Calculator Semantics
Deliverables:
1. Explicit FX realized P&L contract fields and invariants:
 - realized capital P&L explicit zero
 - realized FX P&L explicit and traceable
 - realized total P&L identity
2. Initial policy mode support for realized FX handling with staged rollout for advanced cash-lot cost treatment where required.
3. Cost/valuation/timeseries handoff rules for contract exposure and realized/unrealized separation.
4. `docs/rfc-transaction-specs/transactions/FX/FX-SLICE-6-PNL-SEMANTICS.md`

Exit Criteria:
1. FX realized P&L semantics are explicit and test-enforced.
2. Downstream calculators can consume FX state without inferring hidden semantics.
3. Capital-vs-FX split is deterministic and market-practice aligned.

### Slice 7 - Query, Observability, and OpenAPI Contract Completion
Deliverables:
1. Extend existing transaction/query/support DTOs with FX traceability fields where required.
2. No dedicated FX-only endpoint unless existing surfaces prove insufficient; default approach is to extend current query/support APIs.
3. Full OpenAPI documentation with examples and RFC-0067 vocabulary compliance.
4. Audit/lineage visibility for FX component groups, contract linkage, and swap grouping.
5. `docs/rfc-transaction-specs/transactions/FX/FX-SLICE-7-QUERY-OBSERVABILITY.md`

Exit Criteria:
1. Operators and downstream consumers can inspect FX lifecycle state and linkage evidence using supported APIs/logs.
2. OpenAPI and vocabulary inventory remain complete and canonical.

### Slice 8 - Conformance, Test Suite Wiring, and Exit Report
Deliverables:
1. `scripts/test_manifest.py` suite entries:
 - `transaction-fx-contract`
 - alias `transaction-fx-contract`
2. `Makefile` targets:
 - `test-transaction-fx-contract`
 - `test-transaction-fx-contract`
3. CI matrix wiring for FX contract/conformance coverage.
4. `docs/rfc-transaction-specs/transactions/FX/FX-SLICE-8-CONFORMANCE-REPORT.md`

Exit Criteria:
1. Dedicated FX regression gate exists and runs in CI.
2. Conformance report maps `RFC-FX-01` sections to implementation evidence and accepted residuals.

## Test and Validation Strategy
Per approved slice, run relevant gates:
1. `python -m ruff check ...`
2. `make typecheck`
3. targeted pytest slice suites
4. `python scripts/migration_contract_check.py --mode alembic-sql` (if schema changed)
5. `python scripts/openapi_quality_gate.py` (if API touched)
6. `python scripts/api_vocabulary_inventory.py --output docs/standards/api-vocabulary/lotus-core-api-vocabulary.v1.json` (if API touched)
7. `python scripts/api_vocabulary_inventory.py --validate-only` (if API touched)

Required FX-specific evidence during execution:
1. characterization tests for current non-support baseline;
2. unit tests for validation/linkage/policy helpers;
3. integration tests for persistence/query round trips and calculator behavior;
4. E2E scenarios covering spot, forward, and swap flows with downstream visibility;
5. replay/idempotency tests for multi-component and swap grouping behavior.

## Governance and Standards Alignment
1. No aliases in API contracts or vocabulary inventory (RFC-0067).
2. Canonical snake_case naming only.
3. OpenAPI operation/property documentation completeness required for any new/updated API surface.
4. Docs and code move together in same slice PR.
5. New FX-facing service/runtime behavior must remain aligned with RFC-065 microservice and reliability standards.

## Shared Transaction-Doc Compliance (Mandatory)
Implementation must explicitly follow shared transaction docs under `docs/rfc-transaction-specs/shared/`:
1. `03-normative-rules-and-precedence.md`
2. `04-common-processing-lifecycle.md`
3. `05-common-validation-and-failure-semantics.md`
4. `06-common-calculation-conventions.md`
5. `07-accounting-cash-and-linkage.md`
6. `08-timing-semantics.md`
7. `09-idempotency-replay-and-reprocessing.md`
8. `10-query-audit-and-observability.md`
9. `11-test-strategy-and-gap-assessment.md`
10. `12-canonical-modeling-guidelines.md`
11. `13-dual-leg-accounting-and-cash-adjustment-model.md` (explicitly to document why FX does **not** use the ADJUSTMENT pattern)

### Slice Gate Rule
Every slice PR must include a short shared-doc conformance note listing which shared documents were validated and how.

## Risks and Mitigations
1. Risk: modeling FX settlement using existing ADJUSTMENT logic would produce incorrect reporting semantics.
 - Mitigation: dedicated FX component taxonomy and explicit slice-3 prohibition on ADJUSTMENT reuse.
2. Risk: contract exposure lifecycle could drift from settlement reality, especially for swaps.
 - Mitigation: slice-2 linkage hardening plus slice-4/5 lifecycle tests and replay coverage.
3. Risk: realized FX P&L semantics may be under-specified if advanced cash-lot modes are attempted too early.
 - Mitigation: staged policy rollout with explicit baseline semantics before advanced modes.
4. Risk: API/query drift if FX fields are added ad hoc.
 - Mitigation: slice-7 OpenAPI + vocabulary gate enforcement.

## Open Decisions Requiring Reviewer Direction
1. Spot exposure policy: should phase 1 implement only `spot_exposure_model = NONE` with explicit hooks for later extension, or should spot contract exposure be enabled immediately behind policy?
 - Recommendation: phase 1 defaults to `NONE`; add policy-ready hooks without enabling broad spot contract lifecycle yet.
2. Realized FX P&L policy: should phase 1 support only deterministic baseline modes (`NONE` / `UPSTREAM_PROVIDED`) and stage cash-lot derivation later?
 - Recommendation: yes. Deliver baseline auditable semantics first; stage `CASH_LOT_COST_METHOD` only when requirements are proven and test matrix is ready.
3. FX-related fees/taxes: should phase 1 require separate linked `FEE`/`TAX` postings rather than embedded FX-leg netting?
 - Recommendation: yes. Separate linked postings keep accounting cleaner and align with existing charge-family direction.

## Confirmed Direction
1. FX should be implemented as one coordinated transaction family (`spot`, `forward`, `swap`) because they share contract, linkage, and P&L semantics.
2. FX settlement legs must remain FX-classified and must not be converted into generic `ADJUSTMENT` cash legs.
3. Existing FX rate infrastructure is reusable, but canonical FX transaction processing requires new domain modeling and calculator behavior.
4. Query/support visibility should extend existing surfaces rather than creating unnecessary dedicated endpoints by default.

## Approval Record
1. Plan drafted on `2026-03-09`.
2. Plan approved by requester on `2026-03-09`.
3. Slice 0 and Slice 1 execution started after approval on `2026-03-09`.

## Final Validation Evidence
Local validation completed on the implemented branch:
1. `python scripts/test_manifest.py --suite transaction-fx-contract --quiet`
 - result: `196 passed`
2. `python scripts/test_manifest.py --suite integration-all --quiet`
 - result: `213 passed`
3. `python scripts/test_manifest.py --suite e2e-all --quiet`
 - result: `56 passed`
4. `python scripts/test_manifest.py --suite unit --quiet`
 - result: `862 passed, 6 deselected`
5. `python scripts/test_manifest.py --suite unit-db --quiet`
 - result: `6 passed`
6. `python scripts/test_manifest.py --suite ops-contract --quiet`
 - result: `52 passed`

Targeted regression evidence added during implementation:
1. `tests/e2e/test_fx_lifecycle.py`
2. `tests/unit/libs/portfolio_common/test_fx_validation.py`
3. `tests/unit/libs/portfolio_common/test_fx_linkage.py`
4. `tests/unit/libs/portfolio_common/test_fx_contract_instrument.py`
5. `tests/unit/services/calculators/position_calculator/core/test_position_logic.py`
6. `tests/integration/services/calculators/position_calculator/test_int_position_calc_repo.py`

## Closure Status
1. RFC-082 scope is implemented and locally validated against unit, unit-db, integration, E2E, ops-contract, and dedicated FX contract suites.
2. Remaining future work, if any, should be tracked as additive scope for advanced policy extensions rather than open implementation debt under this RFC.
