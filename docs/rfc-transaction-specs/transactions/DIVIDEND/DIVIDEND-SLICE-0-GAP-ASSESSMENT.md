# DIVIDEND Slice 0 Gap Assessment

## Scope

This assessment captures the baseline gap between current `lotus-core` DIVIDEND behavior and `RFC-DIVIDEND-01` before functional DIVIDEND implementation changes.

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
| Lifecycle stage order (receive -> validate -> normalize -> policy -> calculate -> effects -> persist -> publish -> observability) | PARTIALLY_COVERED | PARTIALLY_MATCHES | Lifecycle spans ingestion/persistence/calculators, but no DIVIDEND-specific stage-state representation or telemetry symmetry with BUY/SELL. | Deterministic DIVIDEND lifecycle with diagnosable stage-state visibility. | Incident/support diagnostics remain weaker for income events. | Add DIVIDEND lifecycle instrumentation and supportability surfaces in Slices 5-6. | Yes |
| DIVIDEND semantic invariant: no quantity change | COVERED | MATCHES | Position calculator default branch leaves quantity/cost unchanged for DIVIDEND. | Same invariant with explicit canonical assertions. | Regression risk during canonical refactor if not locked. | Lock with characterization and invariant tests in Slices 0 and 3. | Yes |
| DIVIDEND must not create/consume lots | PARTIALLY_COVERED | PARTIALLY_MATCHES | Cost engine income strategy does not create lots, but no explicit DIVIDEND lot-invariant guard/reason-code taxonomy exists. | Explicitly enforced "no lot effect" invariant for DIVIDEND. | Silent drift possible if strategy routing changes. | Add explicit invariant checks in Slice 3. | Yes |
| DIVIDEND must recognize gross/net income with withholding visibility | NOT_COVERED | DOES_NOT_MATCH | Current model treats DIVIDEND as generic income cashflow; no canonical withholding/gross/net decomposition fields. | Explicit gross, withholding, net, and reconciliation semantics per RFC-DIVIDEND-01. | Incomplete tax/audit traceability and reconciliation. | Implement canonical decomposition model in Slices 3-4. | Yes |
| Return-of-capital (ROC) policy behavior | NOT_COVERED | DOES_NOT_MATCH | No ROC decomposition or policy-governed basis-adjustment path is currently modeled for DIVIDEND. | ROC component separated and auditable with policy-driven basis effect. | Misclassification risk between income and basis adjustments. | Implement policy-governed ROC path in Slice 4. | Yes |
| DIVIDEND realized P&L invariants (capital/FX/total = 0) | PARTIALLY_COVERED | PARTIALLY_MATCHES | Current income strategy sets realized fields to `None`; explicit canonical zero semantics are not enforced. | Deterministic realized P&L invariant behavior aligned with approved contract semantics. | Ambiguous downstream interpretation and contract drift risk. | Normalize and test canonical realized P&L semantics in Slice 3. | Yes |
| Canonical linkage (`economic_event_id`, `linked_transaction_group_id`) | PARTIALLY_COVERED | PARTIALLY_MATCHES | Metadata columns exist and can propagate if provided, but no DIVIDEND-specific enrichment/defaulting helper exists. | Deterministic linkage id behavior for DIVIDEND with upstream-preserve and default generation. | Weak reconciliation across income and cash effects when metadata missing upstream. | Add DIVIDEND linkage enrichment in Slice 2. | Yes |
| DIVIDEND cash-entry mode support (auto cash leg vs separate external cash entry) | NOT_COVERED | DOES_NOT_MATCH | Current path assumes direct cashflow creation from transaction rule evaluation; no explicit mode contract for external separate cash entry linkage. | Support both cash-entry modes with deterministic linkage and reconciliation behavior. | Integration mismatch with upstream booking patterns and ambiguous settlement reconciliation. | Implement mode-aware cash-entry behavior and linkage enforcement in Slice 4. | Yes |
| Policy id/version traceability for DIVIDEND | NOT_COVERED | DOES_NOT_MATCH | No DIVIDEND-specific policy resolution/enrichment path currently sets canonical policy metadata. | Every DIVIDEND carries policy id/version for reproducibility. | Audit and replay reproducibility gaps. | Implement in Slice 2; enforce via validator in Slice 1. | Yes |
| Failure reason taxonomy with deterministic reason codes | NOT_COVERED | DOES_NOT_MATCH | No DIVIDEND validation module with dedicated reason-code catalog exists. | Deterministic DIVIDEND reason-code taxonomy and strict metadata mode. | Inconsistent QA/support triage and opaque failures. | Deliver DIVIDEND validator + reason codes in Slice 1. | Yes |
| Query surfaces: DIVIDEND state, cash linkage, tax/ROC audit fields | NOT_COVERED | DOES_NOT_MATCH | Generic transaction query exists, but it does not expose full canonical DIVIDEND supportability/audit fields. | Canonical DIVIDEND visibility through existing query/support endpoint contracts (no dedicated DIVIDEND endpoints). | Consumers cannot reliably inspect DIVIDEND canonical state and reconciliation evidence. | Extend existing query/support contracts in Slice 5. | Yes |
| Idempotency/replay safety for DIVIDEND side effects | COVERED | PARTIALLY_MATCHES | Platform idempotency/replay mechanisms exist; DIVIDEND-specific invariants are not explicitly guarded. | Replay-safe DIVIDEND with deterministic metadata and effect invariants. | Duplicate/ambiguous income effects under recovery scenarios. | Add DIVIDEND-specific invariant and replay coverage in Slices 2-4. | Yes |
| Observability diagnosability per DIVIDEND lifecycle stage | NOT_COVERED | DOES_NOT_MATCH | BUY/SELL lifecycle stage metrics exist; DIVIDEND lacks equivalent stage counters and diagnostics views. | Stage-aware DIVIDEND observability and support payloads. | Slower production issue triage for dividend processing incidents. | Add in Slice 5. | No |

## Characterization Coverage Added in Slice 0

- DIVIDEND ingestion DTO baseline behavior lock (`quantity=0`, `price=0`, default `trade_fee`).
- DIVIDEND fee-to-engine transformation behavior lock.
- DIVIDEND cost-engine baseline lock (zero cost, no realized P&L, no lot creation).
- DIVIDEND position baseline lock (no quantity/cost-basis effect).
- DIVIDEND cashflow baseline lock (income classification remains positive inflow).
- DIVIDEND query record mapping lock for current transaction fields.

### Important transition rule

Slice 0 characterization locks current behavior only for refactoring safety.
As implementation slices progress, these tests must be promoted to canonical assertions aligned to `RFC-DIVIDEND-01` final semantics.
No legacy assertion should remain if it conflicts with approved RFC behavior.

## Notes

- This assessment records current behavior and does not modify runtime DIVIDEND logic.
- Functional conformance to `RFC-DIVIDEND-01` begins in Slice 1 onward.
