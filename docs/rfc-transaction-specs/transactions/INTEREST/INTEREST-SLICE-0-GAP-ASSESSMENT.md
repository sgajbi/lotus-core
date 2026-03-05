# INTEREST Slice 0 Gap Assessment

## Scope

This assessment captures the baseline gap between current `lotus-core` INTEREST behavior and `RFC-INTEREST-01` before functional INTEREST implementation changes.

Status labels:

- `COVERED`
- `PARTIALLY_COVERED`
- `NOT_COVERED`

Behavior labels:

- `MATCHES`
- `PARTIALLY_MATCHES`
- `DOES_NOT_MATCH`

## Requirement Matrix

| Requirement | Implementation Status | Behavior Match | Current Observed Behavior | Target Behavior | Risk if Unchanged | Proposed Action | Blocking |
|---|---|---|---|---|---|---|---|
| Lifecycle stage order (receive -> validate -> normalize -> policy -> calculate -> effects -> persist -> publish -> observability) | PARTIALLY_COVERED | PARTIALLY_MATCHES | Lifecycle exists across ingestion/persistence/calculators; no INTEREST-specific stage-state representation and no full observability parity. | Deterministic INTEREST lifecycle with diagnosable stage-state visibility. | Incident/support diagnostics stay weaker for INTEREST events. | Add INTEREST lifecycle instrumentation and supportability surfaces in Slices 5-6. | Yes |
| INTEREST semantic invariant: no quantity change | COVERED | MATCHES | Position calculator default branch leaves quantity/cost unchanged for INTEREST. | Same invariant with explicit canonical assertions. | Regression risk during canonical refactor if not locked. | Lock with characterization in Slice 0 and explicit invariant tests in Slice 3. | Yes |
| INTEREST must not create/consume lots | PARTIALLY_COVERED | PARTIALLY_MATCHES | Cost engine routes INTEREST through generic `IncomeStrategy`; no INTEREST-specific lot invariant checks/reason taxonomy exists. | Explicitly enforced "no lot effect" invariant for INTEREST. | Silent drift possible if strategy routing changes. | Add explicit INTEREST invariants in Slice 3. | Yes |
| INTEREST must support income and expense directions | NOT_COVERED | DOES_NOT_MATCH | No explicit INTEREST direction field/validation; current behavior is effectively income-only via seeded cashflow rule. | Deterministic income/expense direction semantics with explicit contract and validation. | Ambiguous direction handling and reporting inconsistency. | Implement canonical direction semantics in Slices 3-4. | Yes |
| INTEREST must preserve gross/net/withholding decomposition | NOT_COVERED | DOES_NOT_MATCH | Current model treats INTEREST as generic income amount; no canonical withholding decomposition or reconciliation fields. | Explicit gross, withholding, deductions, and net semantics per RFC. | Incomplete tax/audit traceability and reconciliation. | Implement canonical decomposition in Slices 3-4. | Yes |
| INTEREST realized P&L invariants (capital/FX/total = 0) | PARTIALLY_COVERED | PARTIALLY_MATCHES | Current `IncomeStrategy` sets realized P&L fields to `None`, not explicit zero invariants. | Deterministic realized P&L invariants aligned to approved semantics. | Downstream ambiguity and contract drift risk. | Normalize and test canonical realized P&L semantics in Slice 3. | Yes |
| Canonical linkage (`economic_event_id`, `linked_transaction_group_id`) | PARTIALLY_COVERED | PARTIALLY_MATCHES | Linkage fields exist and can propagate if provided; no INTEREST-specific enrichment/defaulting helper exists. | Deterministic linkage behavior with upstream-preserve and stable defaults. | Weak reconciliation across income and cash effects when metadata missing upstream. | Add INTEREST linkage enrichment in Slice 2. | Yes |
| INTEREST cash-entry mode support (auto cash leg vs separate external cash entry) | PARTIALLY_COVERED | PARTIALLY_MATCHES | Generic `cash_entry_mode` fields exist but INTEREST-specific mode enforcement and linkage behavior are not explicit. | Support both cash-entry modes with deterministic linkage/reconciliation. | Integration mismatch with upstream booking patterns and settlement ambiguity. | Implement mode-aware INTEREST behavior in Slice 4. | Yes |
| Policy id/version traceability for INTEREST | NOT_COVERED | DOES_NOT_MATCH | No INTEREST-specific policy resolution/enrichment path currently attaches canonical policy metadata. | Every INTEREST carries policy id/version for reproducibility. | Audit/replay reproducibility gaps. | Implement in Slice 2 and enforce via validator in Slice 1. | Yes |
| Failure reason taxonomy with deterministic reason codes | NOT_COVERED | DOES_NOT_MATCH | No INTEREST validation module or dedicated reason-code catalog exists. | Deterministic INTEREST reason-code taxonomy and strict metadata mode. | Inconsistent QA/support triage and opaque failures. | Deliver INTEREST validator + reason codes in Slice 1. | Yes |
| Query surfaces: INTEREST state, linkage, direction, tax fields | NOT_COVERED | DOES_NOT_MATCH | Generic transaction query exists but does not expose complete canonical INTEREST supportability/audit fields. | Canonical INTEREST visibility through existing query/support endpoints (no dedicated INTEREST endpoints). | Consumers cannot reliably inspect INTEREST state and reconciliation evidence. | Extend existing query/support contracts in Slice 5. | Yes |
| Idempotency/replay safety for INTEREST side effects | COVERED | PARTIALLY_MATCHES | Platform idempotency/replay mechanisms exist, but INTEREST-specific invariants are not explicitly guarded. | Replay-safe INTEREST with deterministic metadata/effect invariants. | Duplicate/ambiguous income effects under recovery scenarios. | Add INTEREST-specific replay/invariant coverage in Slices 2-4. | Yes |
| Observability diagnosability per INTEREST lifecycle stage | NOT_COVERED | DOES_NOT_MATCH | BUY/SELL stage metrics exist; INTEREST lacks equivalent stage counters and diagnostics views. | Stage-aware INTEREST observability and support payloads. | Slower production triage for INTEREST incidents. | Add in Slice 5. | No |

## Characterization Coverage Added in Slice 0

- INTEREST ingestion DTO baseline behavior lock (`quantity=0`, `price=0`, default `trade_fee`).
- INTEREST fee-to-engine transformation behavior lock.
- INTEREST cost-engine baseline lock (zero cost, no realized P&L via current generic strategy, no lot creation).
- INTEREST position baseline lock (no quantity/cost-basis effect).
- INTEREST cashflow baseline lock (income classification remains positive inflow).
- INTEREST query record mapping lock for current transaction fields.

## Shared-Doc Conformance Note (Slice 0)

Validated shared standards for this slice:

- `shared/04-common-processing-lifecycle.md`: matrix tracks lifecycle-stage parity gaps and planned closure slices.
- `shared/05-common-validation-and-failure-semantics.md`: baseline validation gaps captured for reason-code taxonomy work in Slice 1.
- `shared/06-common-calculation-conventions.md`: current numeric behavior locked via characterization tests without semantic rewrite.
- `shared/07-accounting-cash-and-linkage.md`: linkage and cash-entry mode gaps identified with blocking status.
- `shared/10-query-audit-and-observability.md`: query/observability coverage gaps documented for Slice 5.
- `shared/11-test-strategy-and-gap-assessment.md`: characterization-first approach applied before any behavior-changing refactor.

### Important transition rule

Slice 0 characterization locks current behavior only for refactoring safety.
As implementation slices progress, these tests must be promoted to canonical assertions aligned to `RFC-INTEREST-01` final semantics.
No legacy assertion should remain if it conflicts with approved RFC behavior.

## Notes

- This assessment records current behavior and does not modify runtime INTEREST logic.
- Functional conformance to `RFC-INTEREST-01` begins in Slice 1 onward.
