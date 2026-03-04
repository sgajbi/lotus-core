# RFC 059 - BUY Transaction RFC Implementation Plan

## 1. Metadata

- Document ID: RFC-059
- Title: BUY Transaction RFC Implementation Plan
- Version: 1.0.0
- Status: Proposed
- Owner: lotus-core engineering
- Related Specs:
  - `docs/rfc-transaction-specs/transactions/BUY/RFC-BUY-01.md`
  - `docs/rfc-transaction-specs/shared/04-common-processing-lifecycle.md`
  - `docs/rfc-transaction-specs/shared/11-test-strategy-and-gap-assessment.md`
  - `docs/rfc-transaction-specs/shared/12-canonical-modeling-guidelines.md`

## 2. Problem Statement

`RFC-BUY-01` defines a canonical BUY model and behavior that is richer than current `lotus-core` implementation. Current processing supports baseline ingestion, persistence, cost, position, and cashflow, but the BUY specification requires:

- broader canonical fields and metadata
- strict lifecycle-stage traceability
- explicit invariants and reasoned failure semantics
- lot-level and accrued-interest offset behavior
- explicit linkage semantics (`economic_event_id`, `linked_transaction_group_id`)
- stronger policy/version traceability
- expanded query surfaces and test coverage

Without a staged plan, attempting full implementation in one pass risks regressions in core transaction processing, delayed delivery, and unclear verification.

## 3. Domain Intent and Mental Model

From `RFC-BUY-01`, BUY is a deterministic accounting event:

- increases quantity/exposure
- creates cost basis
- consumes cash (or creates explicit external cash expectation)
- creates acquisition lot state
- records accrued-interest offset for eligible instruments
- never realizes P&L at booking time

Lifecycle is mandatory and ordered:

1. receive and ingest
2. validate
3. normalize and enrich
4. resolve policy
5. calculate
6. create business effects
7. persist and publish
8. expose read-model visibility
9. emit observability/support signals

This lifecycle must be visible and diagnosable per transaction.

## 4. Current-State Mapping in lotus-core

### 4.1 Existing components

- Ingestion:
  - `src/services/ingestion_service/app/DTOs/transaction_dto.py`
  - `src/services/ingestion_service/app/routers/transactions.py`
- Persistence:
  - `src/services/persistence_service/app/consumers/transaction_consumer.py`
  - `src/services/persistence_service/app/repositories/transaction_db_repo.py`
  - Shared model: `portfolio_common.database_models.Transaction`
- Calculation:
  - Cost engine consumer: `src/services/calculators/cost_calculator_service/app/consumer.py`
  - Position calculator: `src/services/calculators/position_calculator/app/core/position_logic.py`
  - Cashflow service exists, rule-driven.
- Query:
  - `src/services/query_service/app/routers/transactions.py`
  - `src/services/query_service/app/services/transaction_service.py`

### 4.2 Main gaps vs RFC-BUY-01

- No canonical BUY aggregate model with required sub-model composition.
- Missing core BUY fields at persistence/event level (for example lifecycle, policy metadata, linkage ids, explicit realized P&L schema semantics, accrued-interest offset state).
- No explicit lot domain table/model dedicated to acquisition-lot behavior.
- No explicit accrued-interest offset persistence model/query surface.
- Validation is light compared to RFC-required rules and failure taxonomy.
- Policy resolution is distributed/implicit, not captured as mandatory policy id/version on BUY records.
- Lifecycle stage diagnostics are not exposed as first-class persisted status model.

## 5. Goals and Non-Goals

### 5.1 Goals

- Implement BUY behavior incrementally to conform with `RFC-BUY-01`.
- Preserve service stability and backward compatibility for existing consumers where feasible.
- Establish reusable transaction framework that future RFCs (SELL, DIVIDEND, INTEREST) can reuse.
- Make each slice independently testable and reviewable.

### 5.2 Non-Goals

- Implement non-BUY transaction RFCs in this workstream.
- Perform large unrelated refactors of all transaction paths at once.
- Remove existing endpoints without approved migration path.

## 6. Proposed Architecture and Placement

### 6.1 New logical module boundary (inside existing service layout)

Add a shared transaction domain package under `portfolio_common` to avoid duplicating BUY logic across services:

- `portfolio_common/transaction_domain/`
  - `buy_models.py` (canonical BUY models, field metadata support)
  - `buy_validation.py` (validation rules + reason codes)
  - `buy_policy.py` (policy resolution contract)
  - `buy_calculation.py` (deterministic BUY calculation pipeline)
  - `buy_invariants.py` (post-calculation invariants)
  - `buy_linkage.py` (economic and linked group id generation/validation)

This package is consumed by ingestion/persistence/calculators/query orchestration layers.

### 6.2 Data model additions (expected)

- Extend transaction persistence with canonical BUY metadata fields.
- Add lot state table(s) for acquisition-lot tracking.
- Add accrued-income-offset state table(s), linked to source BUY/lot.
- Add processing-state table or fields to track lifecycle stage and failure semantics.

Exact schema finalized during slice 1/2 design reviews.

### 6.3 Canonical modeling boundaries (mandatory guardrail)

To avoid model drift and overloading a single transaction object, BUY implementation must follow these boundaries.

1. Default transaction model (shared across all transaction types):
   - identity and linkage: `transaction_id`, `transaction_type`, `economic_event_id`, `linked_transaction_group_id`
   - lifecycle core: trade/settlement/booking/value dates and processing status
   - scope references: `portfolio_id`, `instrument_id`, `security_id`
   - currency context: trade/base currency and effective FX context
   - control metadata: policy id/version, source-system traceability, correlation metadata

2. BUY-specific extension model:
   - quantity, execution/clean/dirty price fields
   - fee component inputs
   - accrued-interest input and treatment flags
   - BUY-specific validations and semantic invariants

3. Derived effect models (separate from input contracts):
   - `PositionEffect`
   - `CostBasisEffect`
   - `CashflowEffect`
   - `LotEffect`
   - `AccruedIncomeOffsetEffect`
   - `RealizedPnlEffect` (explicit zeroes for BUY)

4. Reference/domain models (separate bounded context):
   - `Instrument`: master/reference attributes only (identifiers, classification, issuer hierarchy, static reference attributes)
   - `Portfolio`: mandate/base-currency/policy profile context
   - `FxRate` and `MarketPrice`: market reference time-series context
   - Policy catalogs: versioned behavior controls

5. Explicit anti-patterns (not allowed):
   - putting transaction execution/effect state into `Instrument`
   - embedding long-lived lot/offset state directly into raw transaction input contracts
   - mixing canonical shared fields and BUY-only fields without explicit model composition

All Slice 1+ implementation PRs must include a boundary check against this section.

## 7. Incremental Slice Plan

## Slice 0 - Baseline and characterization lock

Scope:

- Build requirement-to-current-state gap matrix for BUY.
- Add characterization tests for currently correct behavior that must not regress.

Deliverables:

- Gap assessment artifact in repo.
- Characterization tests for ingestion, cost, position, and query current BUY path.

Exit criteria:

- Baseline behavior locked by tests.
- Known gaps documented and prioritized.

## Slice 1 - Canonical BUY contract and validation foundation

Scope:

- Introduce canonical BUY models and validation framework (no full behavior switch yet).
- Add reason-code catalog for BUY validation failures.
- Expand ingestion DTO/OpenAPI for canonical BUY input where required.

Deliverables:

- `transaction_domain` model/validation modules.
- Unit tests for all validation rules in this slice.
- OpenAPI updates with descriptions/examples aligned to RFC-0067 style.

Exit criteria:

- New canonical validator runs deterministically.
- Invalid BUY payloads produce explicit reason codes.

## Slice 2 - Persistence, linkage, and policy metadata

Scope:

- Add schema fields for linkage (`economic_event_id`, `linked_transaction_group_id`) and policy metadata.
- Ensure policy id/version and source classification can be traced from stored transaction.
- Ensure idempotent upsert semantics remain intact.

Deliverables:

- Alembic migrations.
- Updated event models and persistence repositories.
- Migration and repository tests.

Exit criteria:

- BUY records persist linkage and policy metadata.
- Replay/idempotency behavior remains stable.

## Slice 3 - BUY calculations and invariants hardening

Scope:

- Implement canonical BUY calculation order and invariant checks.
- Align cost/settlement/book-cost outputs with RFC formulas and policy hooks.
- Emit explicit zero realized P&L fields as required by RFC.

Deliverables:

- Calculation pipeline module integration into cost calculator flow.
- Invariant enforcement with deterministic failure behavior.
- Unit and integration tests (same-currency and cross-currency BUY).

Exit criteria:

- BUY numerical invariants enforced.
- Deterministic outputs for reference vectors.

## Slice 4 - Position, lot, cash, accrued-interest offset behavior

Scope:

- Add lot creation/update behavior for BUY.
- Implement accrued-interest offset initialization and state persistence.
- Ensure cash linkage behavior for auto-generated vs upstream-provided cash modes.
- Ensure held-since and quantity/cost progression compliance.

Deliverables:

- Lot and offset repositories/models/services.
- Cash-linkage enforcement hooks.
- Integration tests for bond/equity scenarios and offset lifecycle init.

Exit criteria:

- BUY creates lot state correctly.
- Accrued offset is initialized and queryable.
- Cash/security effects reconcile by linkage ids.

## Slice 5 - Query/read-model and observability completion

Scope:

- Expose required BUY transaction, lot, cash linkage, and offset query surfaces.
- Add lifecycle/status observability payloads for supportability.
- Ensure stage-level diagnosability and audit trace fields.

Deliverables:

- Query DTO/router/service updates.
- Structured logging and metrics updates for lifecycle stages.
- API tests and supportability checks.

Exit criteria:

- Required RFC query outputs available.
- Lifecycle diagnostics available and test-covered.

## Slice 6 - Full RFC conformance gate

Scope:

- Complete BUY test matrix coverage and gap closure.
- Produce final conformance report against RFC-BUY-01 sections.

Deliverables:

- Conformance checklist with evidence links.
- Regression suite in CI profile for BUY.

Exit criteria:

- All blocking requirements marked covered/matches.
- Residual accepted gaps explicitly approved.

## 8. Testing and Verification Strategy

Testing follows shared `11-test-strategy-and-gap-assessment` categories:

- validation
- calculation
- state changes
- timing
- linkage
- query visibility
- idempotency/replay
- failure modes
- observability

Test pyramid by slice:

- Unit first (models/validators/calculators/invariants)
- Service integration second (consumer + repository + outbox behavior)
- End-to-end flow third (ingest -> persist -> calculators -> query) via docker

Definition of done per slice includes:

- tests added
- deterministic assertions
- no regression in previous slice tests
- docs/OpenAPI sync where contracts changed

### 8.1 Characterization strategy (explicit)

Characterization is two-phase:

1. Baseline characterization (Slice 0):
   - locks currently observed behavior to make refactoring safe.
2. Canonical characterization (Slices 1-6):
   - replaces/updates baseline assertions to lock final behavior defined by `RFC-BUY-01`.

Completion criterion:

- final characterization suite must assert RFC outcomes, not legacy behavior where the two differ.

## 9. Risks and Mitigations

Risk 1: Schema expansion causes compatibility friction.

- Mitigation: additive migrations first, staged adoption, compatibility adapters in service layer.

Risk 2: Hidden coupling across consumers/services causes replay or ordering regressions.

- Mitigation: characterization tests + replay/idempotency tests before behavior switch.

Risk 3: Policy resolution ambiguity leads to inconsistent outputs.

- Mitigation: explicit policy resolver contract with mandatory policy id/version persisted.

Risk 4: Lot/offset semantics introduce accounting drift if partially implemented.

- Mitigation: isolate lot/offset slice with focused integration vectors before broad rollout.

## 10. Assumptions

- BUY is the first transaction type to be brought to canonical target state.
- Existing endpoints remain available during migration unless explicitly deprecated.
- No major cross-service contract break is allowed without separate approval.

## 11. Open Questions for Approval

1. Canonical persistence approach:
   - keep extending existing `transactions` table vs split into `buy_transactions` extension table.
2. Lot persistence granularity:
   - strict lot table from slice 4 vs interim projection derived from existing transaction history.
3. Failure semantics exposure:
   - API-visible reason-code payload now vs internal-only first and API exposure in later slice.
4. Timing policy scope in first BUY delivery:
   - support both trade/settlement timing in first release vs staged enablement.
5. Physical schema strategy for model boundaries:
   - single-table additive extension vs dedicated normalized effect tables by domain (`lot`, `offset`, `cash_linkage`, `processing_state`).

## 12. Slice Tracking Plan

## 12.1 Tracking board format

Use the following board in PR descriptions and weekly status updates:

| Slice | Name | Status | Owner | PRs | Test Gate | Evidence | Notes |
|---|---|---|---|---|---|---|---|
| 0 | Baseline characterization | DONE | lotus-core engineering | merged | local + CI green | `BUY-SLICE-0-GAP-ASSESSMENT.md` + characterization tests | Baseline lock established and used as migration guardrail. |
| 1 | Canonical contract + validation | DONE | lotus-core engineering | merged | local + CI green | `BUY-SLICE-1-VALIDATION-REASON-CODES.md` + validator tests | Deterministic BUY reason-code foundation implemented. |
| 2 | Persistence + linkage + policy metadata | DONE | lotus-core engineering | merged | local + CI green | `BUY-SLICE-2-PERSISTENCE-METADATA.md` + repository tests | Transaction linkage/policy metadata persisted with idempotent updates. |
| 3 | Calculations + invariants | DONE | lotus-core engineering | merged | local + CI green | `BUY-SLICE-3-CALCULATION-INVARIANTS.md` + financial engine tests | Canonical BUY invariants and explicit realized P&L zero behavior enforced. |
| 4 | Position/lot/cash/offset | DONE | lotus-core engineering | merged | local + CI green | `BUY-SLICE-4-LOT-CASH-OFFSET.md` + integration tests | Durable lot and accrued-offset state added with linkage propagation. |
| 5 | Query + observability | DONE | lotus-core engineering | merged | local + CI green | `BUY-SLICE-5-QUERY-OBSERVABILITY.md` + query tests | BUY lot/offset/cash-linkage endpoints and lifecycle telemetry implemented. |
| 6 | Final conformance gate | DONE | lotus-core engineering | merged | local + CI green | `BUY-SLICE-6-CONFORMANCE-REPORT.md` + `buy-rfc` suite | Final section-level conformance map and dedicated CI regression suite added. |

Status values:

- TODO
- IN_PROGRESS
- REVIEW
- BLOCKED
- DONE

## 12.2 Slice review protocol

For each completed slice:

1. Submit slice PR(s) with linked tests and evidence.
2. Update this RFC tracking board.
3. Perform explicit review and approval before moving to next slice.

### 12.3 Tracking requirement for baseline-to-canonical transition

For each baseline characterization test introduced in Slice 0, track one of:

- `UNCHANGED`: behavior already matches RFC and remains locked.
- `UPDATED_TO_CANONICAL`: assertion updated to RFC-defined final behavior.
- `REMOVED_AS_LEGACY`: baseline test retired because legacy behavior is intentionally replaced.

## 13. Final Statement

This RFC defines a controlled implementation plan for `RFC-BUY-01` in `lotus-core`.
No code implementation for BUY behavioral changes should start until this plan is approved.
