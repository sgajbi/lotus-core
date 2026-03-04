# RFC 010 - Test Strategy and Gaps for a Gold-Standard Lotus Core

| Metadata | Value |
| --- | --- |
| Status | Partially Implemented |
| Created | 2025-08-30 |
| Last Updated | 2026-03-04 |
| Owners | lotus-core engineering |
| Depends On | RFC 001, RFC 006, RFC 065, RFC 066 |
| Related Standards | `docs/standards/scalability-availability.md`, `docs/standards/durability-consistency.md` |
| Scope | In repo (`lotus-core`) |

## Executive Summary

RFC 010 extends lotus-core quality from component correctness to system resilience/integrity.
It is partially implemented:
1. Strong unit/integration/e2e baseline exists.
2. Deterministic load and failure-recovery gates exist.
3. Property-based financial invariants are now implemented for cost-basis engines.
4. Remaining advanced goals are broader chaos matrix and offline independent integrity auditor.

## Original Requested Requirements (Preserved)

Original RFC 010 requested:
1. Close foundational test gaps:
   - epoch-aware correctness
   - partial-failure and retry paths
   - stronger financial engine correctness checks
2. Add system-level resilience pillars:
   - chaos testing
   - load/stress testing
   - independent data-integrity auditing
3. Establish production-readiness confidence through repeatable evidence and acceptance gates.

## Current Implementation Reality

Implemented evidence:
1. Outbox retry/partial-failure behavior:
   - `tests/integration/libs/portfolio-common/test_outbox_dispatcher.py`
   - `tests/integration/libs/portfolio-common/test_outbox_dispatcher_delivery_results.py`
2. Consumer idempotency/replay safety:
   - `tests/unit/services/calculators/position_calculator/consumers/test_position_calculator_consumer.py`
   - `tests/unit/services/calculators/cashflow_calculator_service/unit/consumers/test_cashflow_transaction_consumer.py`
3. Workflow-level reliability and reprocessing behavior:
   - `tests/e2e/test_reprocessing_workflow.py`
   - `tests/e2e/test_rapid_reprocessing.py`
   - `tests/e2e/test_failure_scenarios.py`
4. Deterministic resilience/load gates and consolidated signoff:
   - `scripts/performance_load_gate.py`
   - `scripts/failure_recovery_gate.py`
   - `scripts/institutional_signoff_pack.py`
5. Property-based invariant coverage for financial calculator engine:
   - `tests/unit/libs/financial-calculator-engine/unit/test_cost_basis_property_invariants.py`
   - `tests/unit/libs/financial-calculator-engine/unit/test_cost_basis_strategies.py`

Still missing versus original full ambition:
1. No recurring broader chaos suite beyond controlled gate scenarios.
2. No independent offline integrity auditor that recomputes end-state from raw ledger input.

## Requirement-to-Implementation Traceability

| Original Requirement | Current Implementation | Status | Evidence |
| --- | --- | --- | --- |
| Epoch/replay correctness coverage | Strong unit/integration/e2e around reprocessing | Implemented | reprocessing/unit/integration/e2e tests |
| Partial-failure retry validation | Outbox delivery-result tests and consumer error-path tests | Implemented | outbox + consumer tests |
| Load/stress testing pillar | Deterministic load gate script and artifacts | Implemented (initial) | `performance_load_gate.py` |
| Failure injection/recovery testing | Deterministic interruption/recovery gate | Implemented (initial) | `failure_recovery_gate.py` |
| Full chaos matrix automation | Not yet broad/scheduled as requested | Partial gap | backlog delta RFC-010-D01 |
| Independent offline integrity auditor | Not implemented | Gap | backlog delta RFC-010-D02 |
| Property-based financial invariants | Hypothesis-driven invariants for FIFO/AVCO cost-basis logic | Implemented | `tests/unit/libs/financial-calculator-engine/unit/test_cost_basis_property_invariants.py` |

## Design Reasoning and Trade-offs

1. **Why staged implementation**: deterministic gates gave fast operational value while deeper tooling remained open.
2. **Why offline auditor is important**: pipeline-coupled tests can still miss silent drift; independent recomputation provides stronger assurance.
3. **Why property-based tests matter**: financial invariant space is large and example-based tests are insufficient alone; implemented invariants now cover quantity conservation and AVCO split/combined sell consistency.
4. **Trade-off**: advanced resilience tooling increases maintenance cost but directly supports institutional readiness claims.

## Gap Assessment

RFC 010 is still an active roadmap, not a completed milestone.
Open deltas are high-value and still relevant to current platform maturity goals.

## Deviations and Evolution Since Original RFC

1. `review`/`summary` API stress focus in the original text is now less relevant for lotus-core because those endpoints moved to lotus-report.
2. Institutional signoff scripts from RFC 065/066 provide partial realization of system-level test intent.
3. Remaining open work is now concentrated on deeper resilience/auditability, not basic test-pyramid coverage.

## Proposed Changes

1. Keep RFC 010 in `Partially Implemented` status.
2. Execute existing tracked deltas:
   - `RFC-010-D01` chaos suite expansion
   - `RFC-010-D02` independent integrity auditor
3. Tie closure evidence to recurring operational signoff workflows.

## Test and Validation Evidence

1. Unit/integration/e2e baseline:
   - `tests/unit/`
   - `tests/integration/`
   - `tests/e2e/`
2. Property-based invariants:
   - `tests/unit/libs/financial-calculator-engine/unit/test_cost_basis_property_invariants.py`
3. Load/failure deterministic gates:
   - `scripts/performance_load_gate.py`
   - `scripts/failure_recovery_gate.py`
4. Consolidated signoff:
   - `scripts/institutional_signoff_pack.py`

## Original Acceptance Criteria Alignment

Alignment status:
1. Foundational test-gap closure: largely achieved.
2. System can handle controlled failure/recovery scenarios: partially achieved (targeted gate scenarios).
3. Performance baseline gates established: achieved.
4. Property-based financial invariants: achieved.
5. Independent integrity auditor: not achieved.
6. Full system-level resilience suite as initially envisioned: partially achieved.

## Rollout and Backward Compatibility

No runtime API contract change from this documentation retrofit.
Remaining work adds verification capability without breaking existing interfaces.

## Open Questions

1. Should chaos/integrity deltas become merge-blocking or begin as advisory evidence gates?
2. Which environment cadence is mandatory for recurring resilience validation?

## Next Actions

1. Keep RFC 010 classification as `Partially implemented (requires enhancement)`.
2. Execute and close `RFC-010-D01..D02` with concrete code/test artifacts.
