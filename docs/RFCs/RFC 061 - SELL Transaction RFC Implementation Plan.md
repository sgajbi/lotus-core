# RFC 061 - SELL Transaction RFC Implementation Plan

## 1. Metadata

- Document ID: RFC-061
- Title: SELL Transaction RFC Implementation Plan
- Version: 1.0.0
- Status: Implemented
- Owner: lotus-core engineering
- Related Specs:
  - `docs/rfc-transaction-specs/transactions/SELL/RFC-SELL-01.md`
  - `docs/rfc-transaction-specs/shared/04-common-processing-lifecycle.md`
  - `docs/rfc-transaction-specs/shared/11-test-strategy-and-gap-assessment.md`
  - `docs/rfc-transaction-specs/shared/12-canonical-modeling-guidelines.md`
  - `../lotus-platform/rfcs/RFC-0067-centralized-api-vocabulary-inventory-and-openapi-documentation-governance.md`

## 2. Problem Statement

`RFC-SELL-01` defines canonical SELL behavior that is materially richer than current `lotus-core` SELL handling. Current capabilities support baseline transaction ingestion, cost updates, position quantity updates, and valuation integration, but `RFC-SELL-01` requires additional deterministic behavior and evidence:

- explicit disposal semantics and oversell/short-policy control
- deterministic lot-disposal traceability (including methodology and per-lot effects)
- strict realized P&L decomposition (capital, FX, total) with reproducible formulas
- explicit proceeds, settlement, fee, and accrued-interest separation
- mandatory cash-linkage and economic event linkage behavior
- lifecycle-stage observability and failure reason taxonomy
- query surfaces that expose all required state for audit/reconciliation

Without a staged plan, implementing SELL in one pass risks accounting regressions, policy drift, and incomplete validation of disposal invariants.

## 3. Domain Intent and Mental Model

From `RFC-SELL-01`, SELL is a deterministic disposal event:

- reduces position quantity/exposure
- consumes cost basis from lots (or equivalent method state)
- realizes P&L at booking/processing time per policy
- creates or links a settlement cash inflow
- preserves full auditability of disposal, pricing, FX, fees, and accrued-interest components

Lifecycle remains mandatory and ordered:

1. receive and ingest
2. validate
3. normalize and enrich
4. resolve policy
5. calculate
6. create business effects
7. persist and publish
8. expose read-model visibility
9. emit observability/support signals

All lifecycle stages must be diagnosable with deterministic reason codes for failures.

## 4. Current-State Mapping in lotus-core

### 4.1 Existing components reused

- Ingestion:
  - `src/services/ingestion_service/app/DTOs/transaction_dto.py`
  - `src/services/ingestion_service/app/routers/transactions.py`
- Persistence:
  - `src/services/persistence_service/app/consumers/transaction_consumer.py`
  - `src/services/persistence_service/app/repositories/transaction_db_repo.py`
  - shared model: `portfolio_common.database_models.Transaction`
- Calculation:
  - `src/services/calculators/cost_calculator_service/app/consumer.py`
  - `src/services/calculators/position_calculator/app/core/position_logic.py`
  - cashflow generation services
- Query:
  - `src/services/query_service/app/routers/transactions.py`
  - `src/services/query_service/app/services/transaction_service.py`

### 4.2 Known gaps vs RFC-SELL-01

- SELL-specific validation taxonomy is not fully explicit at API level.
- Disposal policy metadata and per-disposal linkage are not fully modeled as first-class fields.
- Realized capital/FX/total decomposition fields require stricter invariant coverage.
- Oversell/short behavior needs explicit policy-driven and test-covered controls.
- Accrued-interest-received separation for fixed income SELL requires clearer persistence and query visibility.
- Full reconciliation-focused query surfaces for lot disposal and cash-linkage need completion.

## 5. Goals and Non-Goals

### 5.1 Goals

- Implement `RFC-SELL-01` in incremental, safe, testable slices.
- Reuse BUY-established transaction framework patterns where valid.
- Keep API contracts fully documented and governed under RFC-0067.
- Ensure deterministic, auditable SELL outcomes for accounting and ops workflows.

### 5.2 Non-Goals

- Implement non-SELL transaction RFCs in this workstream.
- Introduce broad unrelated refactors outside SELL domain boundaries.
- Break existing integrations without explicit migration/deprecation handling.

## 6. Proposed Architecture and Placement

### 6.1 Transaction-domain modules

Extend shared transaction domain under `portfolio_common/transaction_domain/` with SELL modules:

- `sell_models.py`
- `sell_validation.py`
- `sell_policy.py`
- `sell_calculation.py`
- `sell_invariants.py`
- `sell_linkage.py`
- `sell_disposal.py` (lot-disposal method selection and per-lot effect builder)

These modules are consumed by ingestion, persistence, calculators, and query orchestration.

### 6.2 Data model direction

- Extend canonical transaction persistence with SELL-required metadata (policy/version, linkage, disposal context).
- Persist deterministic disposal effects (including lot slices and disposed cost basis trace).
- Persist realized P&L decomposition as explicit fields with invariant checks.
- Persist cash-linkage and accrued-interest-received breakdown where applicable.

### 6.3 Canonical modeling boundaries

1. Shared transaction core (applies to all types): identity, scope, timing, policy trace, source lineage.
2. SELL extension model: disposal-specific inputs and normalized fields.
3. Derived effect models: `PositionEffect`, `CostBasisEffect`, `CashflowEffect`, `LotDisposalEffect`, `RealizedPnlEffect`.
4. Reference/domain models stay separate (`Instrument`, `Portfolio`, `FxRate`, policy catalogs).
5. Anti-pattern guardrails:
   - no embedding of disposal state into instrument masters
   - no mixing raw input and derived disposal effects in a single flat model without typed boundaries

## 7. Incremental Slice Plan

## Slice 0 - Baseline characterization and SELL gap matrix

Scope:

- Build requirement-to-current-state gap matrix for SELL.
- Add characterization tests to lock current behavior where required for safe refactor.

Deliverables:

- `SELL-SLICE-0-GAP-ASSESSMENT.md`
- baseline characterization suite for ingestion, cost, position, and query paths touching SELL

Exit criteria:

- baseline locked and explicit gap list approved.

## Slice 1 - Canonical SELL contract and validation reason codes

Scope:

- Introduce canonical SELL model + validator foundation.
- Define deterministic SELL reason-code taxonomy.
- Update ingestion OpenAPI with complete descriptions/examples/tags/responses.

Deliverables:

- SELL model and validator modules
- reason-code documentation + tests
- OpenAPI updates meeting RFC-0067 quality standards

Exit criteria:

- invalid SELL payloads fail deterministically with explicit reason codes.

## Slice 2 - Persistence, linkage, and policy metadata for disposal

Scope:

- Persist linkage fields (`economic_event_id`, `linked_transaction_group_id`) and policy id/version for SELL.
- Persist disposal-method metadata and deterministic disposal identifiers.
- Keep replay/idempotency behavior stable.

Deliverables:

- migrations + repository updates
- idempotent persistence tests

Exit criteria:

- SELL records and related effects are auditable and linkage-complete.

## Slice 3 - SELL calculation pipeline and invariants

Scope:

- Implement canonical SELL calculation ordering.
- Enforce realized P&L decomposition invariants.
- Enforce proceeds/fee/accrued-interest separation rules.

Deliverables:

- calculation + invariant modules integrated with existing engines
- deterministic vector tests (same currency and cross currency)

Exit criteria:

- all SELL numeric and semantic invariants are test-enforced.

## Slice 4 - Lot disposal, oversell policy, and cash-linkage hardening

Scope:

- Implement deterministic lot disposal behavior per policy.
- Enforce oversell/short handling policy gates.
- Enforce cash-linkage behavior for auto-generated vs upstream-provided cash.

Deliverables:

- disposal effect persistence/query models
- oversell policy tests
- reconciliation tests for security-side vs cash-side linkage

Exit criteria:

- disposal and linkage outcomes are deterministic and reconciled.

## Slice 5 - Query/read model and lifecycle observability completion

Scope:

- Expose required SELL query surfaces (disposals, realized P&L breakdown, linkage, policy trace).
- Add lifecycle state observability for support and audit.
- Ensure ops endpoints align with existing ingestion runbook standards.

Deliverables:

- query DTO/router/service updates
- logs/metrics/traces updates
- integration tests for API outputs and supportability

Exit criteria:

- required audit/reconciliation payloads are available and test-covered.

## Slice 6 - Full SELL conformance gate

Scope:

- Map `RFC-SELL-01` requirements to implementation evidence.
- Add dedicated `sell-rfc` regression suite into CI parity profile.

Deliverables:

- `SELL-SLICE-6-CONFORMANCE-REPORT.md`
- regression suite and CI profile wiring

Exit criteria:

- all blocking RFC requirements marked covered/matches with evidence.

## 8. Testing and Verification Strategy

Test dimensions follow shared transaction strategy:

- validation and reason codes
- calculation and invariants
- lot disposal and state changes
- timing and settlement semantics
- linkage and reconciliation
- query visibility
- idempotency/replay/reprocessing
- failure semantics
- observability/support diagnostics

Test pyramid per slice:

- unit tests for models/validators/calculators/invariants
- service integration tests for consumer/repository/event behavior
- dockerized end-to-end verification for ingest -> persist -> calculate -> query

Definition of done per slice:

- tests added and deterministic
- no regression in previous slice gates
- OpenAPI + vocabulary inventory updated for contract changes
- RFC tracking board updated

## 9. RFC-0067 Governance Requirements for SELL Workstream

Every SELL contract change must include, in the same change cycle:

1. OpenAPI updates with complete summary/description/tags/responses.
2. Every schema property has meaningful description + realistic example + explicit type.
3. Canonical snake_case names only; no aliases or dual naming.
4. Regenerate app inventory in `lotus-core`.
5. Sync inventory to `lotus-platform/platform-contracts/api-vocabulary/lotus-core-api-vocabulary.v1.json`.
6. Run platform cross-app validator before merge.

## 10. Risks and Mitigations

Risk 1: Disposal algorithm changes can drift from expected accounting outcomes.

- Mitigation: reference-vector tests + invariant gates before enabling broader rollout.

Risk 2: Oversell/short handling differences across policies can introduce inconsistent behavior.

- Mitigation: explicit policy matrix tests with deterministic reason codes.

Risk 3: Query/output drift from vocabulary governance.

- Mitigation: enforce RFC-0067 gates on every SELL slice PR.

Risk 4: Coupling between cost, position, and cash modules can cause regressions.

- Mitigation: slice-by-slice rollout with characterization plus end-to-end docker validation.

## 11. Assumptions

- BUY foundation work is complete and reusable for common transaction framework pieces.
- SELL is the next canonical transaction type prioritized after BUY.
- Backward-compatibility requirements remain manageable via additive changes during this phase.

## 12. Open Questions for Approval

1. Disposal persistence granularity:
   - persist full per-lot disposal rows vs compact aggregated disposal trace with reconstruction.
2. Oversell behavior default in initial delivery:
   - strict reject only vs policy-driven optional short-enabled mode from slice 1.
3. Accrued-interest-received reporting shape:
   - expose as separate query section vs flattened realized breakdown fields.
4. Realized FX decomposition storage:
   - persist all intermediate components vs only final deterministic outputs with reproducible inputs.

## 13. Slice Tracking Plan

| Slice | Name | Status | Owner | PRs | Test Gate | Evidence | Notes |
|---|---|---|---|---|---|---|---|
| 0 | Baseline characterization | DONE | lotus-core engineering | pending | local green | `SELL-SLICE-0-GAP-ASSESSMENT.md` + `test_sell_slice0_characterization.py` | Baseline lock established and gap matrix captured. |
| 1 | Canonical contract + validation | DONE | lotus-core engineering | pending | local green | `SELL-SLICE-1-VALIDATION-REASON-CODES.md` + `test_sell_validation.py` | Deterministic SELL reason-code foundation implemented in transaction domain. |
| 2 | Persistence + linkage + policy metadata | DONE | lotus-core engineering | pending | local green | `SELL-SLICE-2-PERSISTENCE-METADATA.md` + `test_sell_linkage.py` | Deterministic SELL linkage/policy metadata enrichment integrated pre-persistence. |
| 3 | Calculations + invariants | DONE | lotus-core engineering | pending | local green | `SELL-SLICE-3-CALCULATION-INVARIANTS.md` + `test_cost_calculator.py` | SELL proceeds/consumption/sign invariants enforced in cost engine with deterministic errors. |
| 4 | Lot disposal + oversell + cash linkage | DONE | lotus-core engineering | pending | local green | `SELL-SLICE-4-DISPOSAL-CASH-LINKAGE.md` + linkage/consumer/cost tests | Deterministic disposal policy tagging and strict oversell gates added with linkage propagation checks. |
| 5 | Query + observability | DONE | lotus-core engineering | merged | local + CI green | `SELL-SLICE-5-QUERY-OBSERVABILITY.md` + sell query tests | SELL disposal/cash-linkage APIs and lifecycle telemetry implemented. |
| 6 | Final conformance gate | DONE | lotus-core engineering | merged | local + CI green | `SELL-SLICE-6-CONFORMANCE-REPORT.md` + `sell-rfc` suite | Final section-level conformance evidence and dedicated CI regression suite added. |

Status values: `TODO`, `IN_PROGRESS`, `REVIEW`, `BLOCKED`, `DONE`.

## 14. Final Statement

This RFC defines a controlled implementation plan for `RFC-SELL-01` in `lotus-core`.
Implementation should proceed slice-by-slice with explicit approval checkpoints.
