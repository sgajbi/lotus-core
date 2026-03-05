# RFC 069 - DIVIDEND Transaction RFC Implementation Plan

| Field | Value |
| --- | --- |
| Status | In Progress |
| Created | 2026-03-05 |
| Last Updated | 2026-03-05 |
| Owners | lotus-core engineering |
| Depends On | `docs/rfc-transaction-specs/transactions/DIVIDEND/RFC-DIVIDEND-01.md`; shared transaction lifecycle specs |
| Related Standards | RFC-0067 OpenAPI/vocabulary governance; durability/consistency and rounding standards |
| Scope | In repo |

## Executive Summary
This RFC defines the implementation plan for canonical `DIVIDEND` processing in `lotus-core`, following the same slice-based delivery pattern used for BUY (`RFC 059`) and SELL (`RFC 061`).

Current `DIVIDEND` behavior is functional but minimal:
1. cost engine treats DIVIDEND as generic income with zero net cost and no realized P&L decomposition;
2. position engine keeps quantity/cost unchanged for DIVIDEND;
3. cashflow engine creates positive income inflow from gross amount;
4. no DIVIDEND-specific canonical validation taxonomy, policy/linkage enrichment, or dedicated query supportability surface exists yet.

This plan closes those gaps incrementally with deterministic validation, policy/linkage traceability, richer calculation semantics (gross/net/withholding/ROC), and conformance gates.

Quality target:
1. industry-grade accounting/analytics semantics (not minimal functional parity only);
2. deterministic and reproducible numeric behavior suitable for audit, reconciliation, and downstream quant analytics;
3. explicit decomposition fields aligned to market practice (gross income, withholding, ROC component, net cash effect);
4. standards-grade contracts/tests with strict governance gates.

## Original Requested Requirements (Preserved)
1. Implement `RFC-DIVIDEND-01` semantics without regressing existing BUY/SELL behavior.
2. Introduce canonical DIVIDEND validation reason codes and strict metadata support.
3. Ensure deterministic linkage and policy metadata (`economic_event_id`, `linked_transaction_group_id`, policy id/version) for DIVIDEND.
4. Implement explicit DIVIDEND calculation invariants:
 - no quantity change
 - no lot creation/consumption
 - no realized capital/FX P&L
 - explicit gross/net/withholding handling
5. Implement dual cash-entry mode behavior for DIVIDEND, consistent with BUY/SELL integration patterns:
 - auto-generated cash leg mode
 - separate external cash entry mode
 - deterministic linkage across income and cash legs
6. Ensure cash-linkage and reconciliation behavior is auditable and queryable.
7. Add dedicated DIVIDEND regression suite and CI wiring equivalent to `buy-rfc`/`sell-rfc`.
8. Produce a slice-6 conformance report mapping `RFC-DIVIDEND-01` requirements to code/tests.

## Current Implementation Reality (Baseline)
1. Transaction type exists in engine enum and processing (`DIVIDEND`).
2. Ingestion allows DIVIDEND with `quantity=0` and `price=0` payload pattern.
3. Cost calculation currently routes DIVIDEND to generic `IncomeStrategy` with:
 - `net_cost = 0`, `net_cost_local = 0`, `gross_cost = 0`
 - realized P&L fields left `None`.
4. Position logic does not alter quantity/cost for DIVIDEND (default non-position-impact branch).
5. Cashflow logic classifies DIVIDEND as income inflow but does not model withholding-tax or ROC decomposition.
6. BUY/SELL have dedicated transaction-domain models/validators/reason-codes/linkage helpers and query-state surfaces; DIVIDEND has none yet.

## Requirement-to-Implementation Gap Matrix
| Requirement | Current State | Gap | Planned Slice |
| --- | --- | --- | --- |
| DIVIDEND canonical validation taxonomy | Not implemented | No DIVIDEND reason codes/validator module | Slice 1 |
| Strict metadata validation for DIVIDEND | Not implemented | No DIVIDEND canonical model with strict metadata checks | Slice 1 |
| Deterministic policy/linkage enrichment | Not implemented | No DIVIDEND metadata enrichment helper in processing pipeline | Slice 2 |
| Dual cash-entry mode (auto cash leg vs separate external cash entry) | Not implemented | No explicit DIVIDEND cash-entry mode model and linkage enforcement | Slice 4 |
| Explicit DIVIDEND invariants in cost engine | Partially implemented | Generic income strategy lacks explicit DIVIDEND invariant/error semantics and realized P&L explicit-zero treatment | Slice 3 |
| Withholding/ROC decomposition model | Not implemented | No canonical fields/logic for gross/net/withholding/ROC components | Slice 3-4 |
| Cash-linkage + reconciliation supportability | Partially implemented | Basic cashflow exists; no dedicated DIVIDEND linkage/query contract | Slice 4-5 |
| DIVIDEND query-state surfaces | Not implemented | No DIVIDEND-specific router/DTO/repository/service surfaces | Slice 5 |
| Dedicated regression suite + CI alias | Not implemented | No `transaction-dividend-contract` / `dividend-rfc` suite | Slice 6 |
| RFC conformance mapping report | Not implemented | No section-to-evidence closure artifact | Slice 6 |

## Slice Plan (0..6)

## Slice Execution Status
| Slice | Status | Evidence |
| --- | --- | --- |
| 0 | Completed | `DIVIDEND-SLICE-0-GAP-ASSESSMENT.md`, characterization tests |
| 1 | Completed | `DIVIDEND-SLICE-1-VALIDATION-REASON-CODES.md`, validator/reason-code tests |
| 2 | Completed | `DIVIDEND-SLICE-2-PERSISTENCE-METADATA.md`, enrichment + consumer tests |
| 3 | Completed | `DIVIDEND-SLICE-3-CALCULATION-INVARIANTS.md`, cost invariant tests |
| 4 | Completed | `DIVIDEND-SLICE-4-WITHHOLDING-ROC-CASH-LINKAGE.md`, cash-entry mode/linkage tests |
| 5 | Completed | `DIVIDEND-SLICE-5-QUERY-OBSERVABILITY.md`, query/API governance evidence |
| 6 | Pending | Conformance suite wiring and closure report |

### Slice 0 - Gap Assessment and Characterization Baseline (docs + tests, no behavior change)
Deliverables:
1. `docs/rfc-transaction-specs/transactions/DIVIDEND/DIVIDEND-SLICE-0-GAP-ASSESSMENT.md`
2. Characterization tests for current DIVIDEND behavior (ingestion, cost, cashflow, position non-impact).
3. Explicit transition note: characterization assertions must be replaced where canonical behavior diverges.

Exit Criteria:
1. Baseline behavior is locked to prevent accidental regressions during refactor.
2. Gap matrix clearly identifies blocking vs non-blocking deltas.

### Slice 1 - Canonical DIVIDEND Validation + Reason Codes
Deliverables:
1. `portfolio_common.transaction_domain.dividend_models`
2. `portfolio_common.transaction_domain.dividend_reason_codes`
3. `portfolio_common.transaction_domain.dividend_validation`
4. Tests mirroring BUY/SELL validator coverage patterns.
5. `docs/rfc-transaction-specs/transactions/DIVIDEND/DIVIDEND-SLICE-1-VALIDATION-REASON-CODES.md`

Exit Criteria:
1. Deterministic reason-code taxonomy exists.
2. Strict metadata validation mode exists and is tested.

### Slice 2 - Metadata Enrichment and Persistence Traceability
Deliverables:
1. DIVIDEND metadata enrichment helper (`economic_event_id`, linkage group, policy id/version defaults).
2. Cost-calculator consumer integration with DIVIDEND enrichment path.
3. Persistence verification tests showing metadata survives end-to-end.
4. `docs/rfc-transaction-specs/transactions/DIVIDEND/DIVIDEND-SLICE-2-PERSISTENCE-METADATA.md`

Exit Criteria:
1. Upstream metadata is preserved when supplied.
2. Deterministic defaults are applied when absent.

### Slice 3 - Calculation Invariants and Deterministic DIVIDEND Semantics
Deliverables:
1. DIVIDEND-specific invariant checks in cost calculation path.
2. Explicit realized P&L semantics aligned to RFC-DIVIDEND-01 (capital/FX/total explicitly zero in canonical representation where applicable).
3. Validation/calc tests for:
 - quantity invariant (`quantity_delta = 0`)
 - no lot effects
 - no realized capital/FX P&L
 - gross/net amount constraints
4. `docs/rfc-transaction-specs/transactions/DIVIDEND/DIVIDEND-SLICE-3-CALCULATION-INVARIANTS.md`

Exit Criteria:
1. DIVIDEND semantics are explicit and test-enforced, not implicit via generic income fallback.

### Slice 4 - Withholding/ROC and Cash-Linkage Accounting
Deliverables:
1. Canonical modeling and persistence support for withholding tax and optional ROC decomposition fields.
2. Canonical DIVIDEND cash-entry mode support:
 - auto-generated cash leg mode (service creates linked cashflow)
 - separate external cash entry mode (service records explicit expected linkage to upstream cash entry)
3. Cashflow linkage hardening for DIVIDEND settlement reconciliation (`economic_event_id`, linkage group, mode-aware linkage state).
4. Tests validating gross/net/withholding reconciliation, mode behavior, and cash-link consistency.
4. `docs/rfc-transaction-specs/transactions/DIVIDEND/DIVIDEND-SLICE-4-WITHHOLDING-ROC-CASH-LINKAGE.md`

Exit Criteria:
1. DIVIDEND income and cash effects reconcile deterministically.
2. ROC policy path is explicit and auditable.
3. Both cash-entry modes are supported with deterministic linkage and replay-safe behavior.

### Slice 5 - Query and Observability Supportability Surfaces
Deliverables:
1. Extend existing query DTOs/repository/service contracts to expose DIVIDEND canonical fields and linkage evidence.
2. Reuse existing transaction/support endpoints; do not introduce DIVIDEND-dedicated endpoints.
3. OpenAPI-complete contract updates (`summary`, `description`, responses, examples) per RFC-0067.
4. Lifecycle/diagnostic telemetry for DIVIDEND path in calculator service.
5. `docs/rfc-transaction-specs/transactions/DIVIDEND/DIVIDEND-SLICE-5-QUERY-OBSERVABILITY.md`

Exit Criteria:
1. Operators and downstream consumers can inspect DIVIDEND state and linkage evidence through existing supported APIs/logs.

### Slice 6 - Conformance, Suite Wiring, and Exit Report
Deliverables:
1. `scripts/test_manifest.py` suite entries:
 - `transaction-dividend-contract`
 - alias `dividend-rfc`
2. `Makefile` targets:
 - `test-transaction-dividend-contract`
 - `test-dividend-rfc`
3. CI matrix wiring for `dividend-rfc`.
4. `docs/rfc-transaction-specs/transactions/DIVIDEND/DIVIDEND-SLICE-6-CONFORMANCE-REPORT.md`

Exit Criteria:
1. Dedicated DIVIDEND regression gate exists and runs in CI.
2. Conformance report maps RFC-DIVIDEND-01 sections to implementation evidence and accepted residuals.

## Test and Validation Strategy
Per approved slice, run relevant gates:
1. `python -m ruff check ...`
2. `make typecheck`
3. targeted pytest slice suites
4. `python scripts/migration_contract_check.py --mode alembic-sql` (if schema changed)
5. `python scripts/openapi_quality_gate.py` (if API touched)
6. `python scripts/api_vocabulary_inventory.py --output docs/standards/api-vocabulary/lotus-core-api-vocabulary.v1.json` (if API touched)
7. `python scripts/api_vocabulary_inventory.py --validate-only` (if API touched)

If vocabulary changes are synchronized to platform catalog:
1. run `lotus-platform/platform-contracts/api-vocabulary/validate_api_vocabulary_catalog.py`

Quantitative and Analytics Rigor gates:
1. all monetary computations must remain decimal-safe with policy-defined precision/rounding;
2. decomposition identities must be test-enforced (for example `net = gross - withholding - deductions`, ROC separation where applicable);
3. reconciliation tests must verify deterministic linkage between income leg and cash leg across both cash-entry modes;
4. replay tests must prove identical outputs for identical inputs/policy and deterministic conflict handling for materially inconsistent duplicates;
5. output contracts must be analytics-ready (explicit component fields, no ambiguous overloaded totals).

## Governance and Standards Alignment
1. No aliases in API contracts or vocabulary inventory (RFC-0067).
2. Canonical snake_case naming only.
3. OpenAPI operation/property documentation completeness required for any new/updated API surface.
4. Docs and code move together in same slice PR.

## Shared Transaction-Doc Compliance (Mandatory)
Implementation must explicitly follow shared transaction docs under `docs/rfc-transaction-specs/shared/`:
1. `03-normative-rules-and-precedence.md`
 - Use precedence order for conflict resolution (transaction-specific rules > policy > shared rules).
2. `04-common-processing-lifecycle.md`
 - Preserve canonical lifecycle stage order; do not remove/reorder stages.
3. `05-common-validation-and-failure-semantics.md`
 - Map DIVIDEND failures to standard outcomes and emit stage + reason + correlation/linkage metadata.
4. `06-common-calculation-conventions.md`
 - Use decimal-safe arithmetic and define explicit zero-vs-not-applicable realized P&L semantics.
5. `07-accounting-cash-and-linkage.md`
 - Implement dual-accounting requirements, including both cash-entry modes and explicit linkage model.
6. `08-timing-semantics.md`
 - Define TRADE_DATE vs SETTLEMENT_DATE behavior for income recognition and cash settlement visibility.
7. `09-idempotency-replay-and-reprocessing.md`
 - Ensure deterministic replay and define conflict handling for same business event with changed payload.
8. `10-query-audit-and-observability.md`
 - Expose enriched transaction, derived state, linkage state, policy metadata, and audit metadata.
9. `11-test-strategy-and-gap-assessment.md`
 - Keep full gap matrix and mandatory test categories per slice.
10. `12-canonical-modeling-guidelines.md`
 - Build DIVIDEND canonical model from reusable sub-models with field metadata classifications.

### Slice Gate Rule
Every slice PR must include a short "shared-doc conformance note" listing which of the above shared documents were touched and how compliance was validated.

## Risks and Mitigations
1. Risk: semantic drift between generic income handling and canonical DIVIDEND invariants.
 - Mitigation: slice-3 invariant hardening + explicit regression cases.
2. Risk: withholding/ROC expansion increases model complexity.
 - Mitigation: additive schema approach, strict tests, and staged rollout.
3. Risk: cross-service interpretation mismatch (gateway/report consumers).
 - Mitigation: RFC-0067-compliant contracts and vocabulary gate updates when API changes.

## Open Decisions Requiring Reviewer Direction
1. For DIVIDEND realized P&L fields, should canonical contract enforce explicit numeric zero fields everywhere, or allow `None` internally with zero at external contract boundaries?
2. Should ROC be implemented in baseline slice-4 scope as fully active behavior, or introduced behind explicit policy flag with default disabled behavior?

## Confirmed Direction
1. DIVIDEND delivery must not add dedicated endpoints.
2. DIVIDEND visibility must be delivered by extending existing query/support endpoint contracts.

## Approval Gate (No Implementation Before Approval)
Implementation work must not start until this plan is approved.

Approval checklist:
1. Slice boundaries accepted.
2. Open decisions resolved.
3. Test/gate expectations accepted.
4. Residual-risk acceptance criteria confirmed.

## Industry-Grade Acceptance Criteria
To close RFC 069 as implemented, evidence must show:
1. accounting correctness and reconciliation completeness under realistic wealth-management scenarios (gross/net/withholding/ROC/cash-linkage);
2. deterministic behavior under reprocessing/idempotency conflict paths;
3. contract quality and vocabulary governance compliance (RFC-0067) with no alias drift;
4. robust unit + integration coverage focused on domain outcomes, not status-code-only assertions;
5. clear operational diagnostics for support teams (failure codes, stage, correlation/linkage metadata).

## Next Actions After Approval
1. Execute Slice 0 and publish `DIVIDEND-SLICE-0-GAP-ASSESSMENT.md`.
2. Proceed slice-by-slice with evidence in each PR.
3. Stop after each slice for validation results and go/no-go confirmation.
