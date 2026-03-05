# RFC 070 - INTEREST Transaction RFC Implementation Plan

| Field | Value |
| --- | --- |
| Status | In Progress |
| Created | 2026-03-05 |
| Last Updated | 2026-03-05 |
| Owners | lotus-core engineering |
| Depends On | `docs/rfc-transaction-specs/transactions/INTEREST/RFC-INTEREST-01.md`; shared transaction lifecycle specs |
| Related Standards | RFC-0067 OpenAPI/vocabulary governance; durability/consistency and rounding standards |
| Scope | In repo |

## Executive Summary
This RFC defines the implementation plan for canonical `INTEREST` processing in `lotus-core`, following the same slice-based delivery pattern established for BUY (`RFC 059`), SELL (`RFC 061`), and DIVIDEND (`RFC 069`).

Current `INTEREST` behavior is functional but generic:
1. transaction type is supported by the financial engine enum and calculator routing;
2. cashflow rules seed `INTEREST` as `INCOME` classification;
3. cost engine routes `INTEREST` through generic `IncomeStrategy`;
4. there is no INTEREST-specific canonical validation taxonomy, metadata enrichment, policy traceability, or dedicated conformance suite.

This plan closes those gaps incrementally with deterministic validation, explicit income/expense semantics, policy/linkage traceability, and standards-grade conformance evidence.

## Original Requested Requirements (Preserved)
1. Implement `RFC-INTEREST-01` semantics without regressing existing BUY/SELL/DIVIDEND behavior.
2. Add canonical INTEREST validation reason codes and strict metadata support.
3. Ensure deterministic linkage and policy metadata (`economic_event_id`, `linked_transaction_group_id`, policy id/version) for INTEREST.
4. Implement explicit INTEREST calculation invariants:
 - no quantity impact
 - no lot creation/consumption
 - explicit zero realized capital/FX P&L
 - deterministic gross/net/withholding handling
5. Implement dual cash-entry mode behavior (auto cash leg vs upstream-provided linked cash entry) with deterministic linkage.
6. Support explicit interest direction semantics (income vs expense) aligned to market practice and reporting requirements.
7. Extend existing query/observability surfaces for INTEREST lifecycle supportability (no transaction-specific dedicated endpoints).
8. Deliver dedicated INTEREST regression suite and conformance report.

## Current Implementation Reality (Baseline)
1. `INTEREST` exists in `TransactionType` enum and is processable in core engine pipelines.
2. `cashflow_rules` includes a seeded `INTEREST` rule under `INCOME`.
3. Cost calculator uses generic `IncomeStrategy` for `INTEREST` (no INTEREST-specific invariant taxonomy).
4. No `portfolio_common.transaction_domain.interest_*` model/validator/reason-code modules exist.
5. No INTEREST-specific metadata enrichment helper exists in calculator consumers.
6. No INTEREST-specific transaction contract suite (`interest-rfc`) exists in test manifest/CI.

## Requirement-to-Implementation Gap Matrix
| Requirement | Current State | Gap | Planned Slice |
| --- | --- | --- | --- |
| Canonical INTEREST validation taxonomy | Not implemented | No INTEREST reason codes/validator module | Slice 1 |
| Strict metadata validation for INTEREST | Not implemented | No INTEREST canonical model with strict metadata checks | Slice 1 |
| Deterministic policy/linkage enrichment | Not implemented | No INTEREST enrichment helper in processing pipeline | Slice 2 |
| Explicit INTEREST invariants in cost engine | Partially implemented | Generic income fallback lacks INTEREST-specific error semantics | Slice 3 |
| Income vs expense direction contract | Not implemented | No canonical direction field/validation/policy defaults | Slice 3-4 |
| Dual cash-entry mode linkage behavior | Partially implemented | DIVIDEND-only explicit handling today; INTEREST mode behavior not explicit | Slice 4 |
| Query/observability supportability | Partially implemented | Generic transaction query only; no INTEREST-focused traceability coverage | Slice 5 |
| Dedicated INTEREST regression suite + CI alias | Not implemented | No `transaction-interest-contract` / `interest-rfc` suite wiring | Slice 6 |
| INTEREST conformance closure report | Not implemented | No RFC-to-evidence closure artifact | Slice 6 |

## Slice Plan (0..6)

## Slice Execution Status
| Slice | Status | Evidence |
| --- | --- | --- |
| 0 | Completed | `docs/rfc-transaction-specs/transactions/INTEREST/INTEREST-SLICE-0-GAP-ASSESSMENT.md`, `tests/unit/transaction_specs/test_interest_slice0_characterization.py` |
| 1 | Completed | `docs/rfc-transaction-specs/transactions/INTEREST/INTEREST-SLICE-1-VALIDATION-REASON-CODES.md`, `tests/unit/libs/portfolio_common/test_interest_validation.py` |
| 2 | Completed | `docs/rfc-transaction-specs/transactions/INTEREST/INTEREST-SLICE-2-PERSISTENCE-METADATA.md`, `tests/unit/libs/portfolio_common/test_interest_linkage.py`, `tests/integration/services/persistence_service/repositories/test_repositories.py` |
| 3 | Pending | Calculation invariants + direction semantics baseline |
| 4 | Pending | Cash-entry mode + withholding/linkage behavior |
| 5 | Pending | Query/observability supportability artifacts |
| 6 | Pending | Conformance suite wiring + closure report |

### Slice 0 - Gap Assessment and Characterization Baseline (docs + tests, no behavior change)
Deliverables:
1. `docs/rfc-transaction-specs/transactions/INTEREST/INTEREST-SLICE-0-GAP-ASSESSMENT.md`
2. Characterization tests for current INTEREST ingestion/cost/cashflow/position behavior.
3. Explicit transition note for assertions expected to change under canonical behavior.

Exit Criteria:
1. Baseline behavior is locked to prevent accidental regressions during refactor.
2. Blocking and non-blocking deltas are explicitly cataloged.

### Slice 1 - Canonical INTEREST Validation + Reason Codes
Deliverables:
1. `portfolio_common.transaction_domain.interest_models`
2. `portfolio_common.transaction_domain.interest_reason_codes`
3. `portfolio_common.transaction_domain.interest_validation`
4. Tests mirroring BUY/SELL/DIVIDEND validator coverage patterns.
5. `docs/rfc-transaction-specs/transactions/INTEREST/INTEREST-SLICE-1-VALIDATION-REASON-CODES.md`

Exit Criteria:
1. Deterministic INTEREST reason-code taxonomy exists.
2. Strict metadata validation mode exists and is tested.

### Slice 2 - Metadata Enrichment and Persistence Traceability
Deliverables:
1. INTEREST metadata enrichment helper for linkage/policy fields.
2. Cost-calculator consumer integration with INTEREST enrichment path.
3. Persistence verification tests showing metadata survives end-to-end.
4. `docs/rfc-transaction-specs/transactions/INTEREST/INTEREST-SLICE-2-PERSISTENCE-METADATA.md`

Exit Criteria:
1. Upstream metadata is preserved when supplied.
2. Deterministic defaults are applied when absent.

### Slice 3 - Calculation Invariants and Direction Semantics
Deliverables:
1. INTEREST-specific invariant checks in cost calculation path.
2. Explicit realized P&L zero semantics for INTEREST.
3. Canonical direction semantics baseline (`income` vs `expense`) with deterministic validation and mapping rules.
4. `docs/rfc-transaction-specs/transactions/INTEREST/INTEREST-SLICE-3-CALCULATION-INVARIANTS.md`

Exit Criteria:
1. INTEREST semantics are explicit and test-enforced, not implicit generic fallback.
2. Direction behavior is deterministic and auditable.

### Slice 4 - Cash-Entry Mode, Withholding, and Linkage Accounting
Deliverables:
1. INTEREST cash-entry mode behavior parity with canonical transaction model:
 - auto-generated cash leg mode
 - upstream-provided linked cash entry mode
2. Withholding and net-interest reconciliation identities in canonical contract.
3. Cashflow consumer handling for INTEREST external mode linkage.
4. `docs/rfc-transaction-specs/transactions/INTEREST/INTEREST-SLICE-4-CASH-LINKAGE-WITHHOLDING.md`

Exit Criteria:
1. INTEREST accounting and cash effects reconcile deterministically.
2. Both cash-entry modes are replay-safe and audit-friendly.

### Slice 5 - Query and Observability Supportability Surfaces
Deliverables:
1. Extend existing transaction query contracts to expose INTEREST linkage/direction evidence where required.
2. Reuse existing query/support endpoints; no INTEREST-dedicated endpoints.
3. OpenAPI-complete contract updates and RFC-0067 vocabulary compliance.
4. `docs/rfc-transaction-specs/transactions/INTEREST/INTEREST-SLICE-5-QUERY-OBSERVABILITY.md`

Exit Criteria:
1. Operators and downstream consumers can inspect INTEREST state/linkage evidence via supported APIs/logs.

### Slice 6 - Conformance, Suite Wiring, and Exit Report
Deliverables:
1. `scripts/test_manifest.py` suite entries:
 - `transaction-interest-contract`
 - alias `interest-rfc`
2. `Makefile` targets:
 - `test-transaction-interest-contract`
 - `test-interest-rfc`
3. CI matrix wiring for `interest-rfc`.
4. `docs/rfc-transaction-specs/transactions/INTEREST/INTEREST-SLICE-6-CONFORMANCE-REPORT.md`

Exit Criteria:
1. Dedicated INTEREST regression gate exists and runs in CI.
2. Conformance report maps RFC-INTEREST-01 sections to implementation evidence and accepted residuals.

## Test and Validation Strategy
Per approved slice, run relevant gates:
1. `python -m ruff check ...`
2. `make typecheck`
3. targeted pytest slice suites
4. `python scripts/migration_contract_check.py --mode alembic-sql` (if schema changed)
5. `python scripts/openapi_quality_gate.py` (if API touched)
6. `python scripts/api_vocabulary_inventory.py --output docs/standards/api-vocabulary/lotus-core-api-vocabulary.v1.json` (if API touched)
7. `python scripts/api_vocabulary_inventory.py --validate-only` (if API touched)

## Governance and Standards Alignment
1. No aliases in API contracts or vocabulary inventory (RFC-0067).
2. Canonical snake_case naming only.
3. OpenAPI operation/property documentation completeness required for any new/updated API surface.
4. Docs and code move together in same slice PR.

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

### Slice Gate Rule
Every slice PR must include a short shared-doc conformance note listing which shared documents were validated and how.

## Risks and Mitigations
1. Risk: semantic drift between generic income handling and canonical INTEREST invariants.
 - Mitigation: slice-3 invariant hardening and explicit regression tests.
2. Risk: direction and withholding semantics introduce contract ambiguity.
 - Mitigation: explicit canonical fields + reason codes + reconciliation identities.
3. Risk: cross-service interpretation mismatch for cash-linkage mode.
 - Mitigation: shared cash-entry mode utility reuse and end-to-end contract tests.

## Open Decisions Requiring Reviewer Direction
1. Should INTEREST direction be encoded as explicit canonical field (`interest_direction`) while keeping transaction_type=`INTEREST` for both income and expense?
2. Should withholding and other deductions be modeled as additive canonical fields in the transaction contract now, or staged behind policy feature flags?
3. Should INTEREST expense path reuse existing `EXPENSE` cashflow classification rules immediately, or be introduced in a staged rule migration?

## Confirmed Direction
1. INTEREST implementation should follow existing transaction RFC delivery discipline (slice-based, evidence-first).
2. INTEREST visibility should be delivered via existing query/support endpoint surfaces (no dedicated transaction endpoint by default).

## Approval Record
1. Plan approved by requester on `2026-03-05` and Slice 0 execution started.

## Approval Gate (Closed)
Implementation started after plan approval.

Approval checklist:
1. Slice boundaries accepted.
2. Open decisions to be finalized during execution.
3. Test/gate expectations accepted.
4. Residual-risk acceptance criteria confirmed.
