# RFC 006 - Fortify Data Integrity and Enhance Unit Test Suite

| Metadata | Value |
| --- | --- |
| Status | Implemented |
| Created | 2025-08-29 |
| Last Updated | 2026-03-04 |
| Owners | lotus-core engineering |
| Depends On | RFC 005 |
| Related Standards | `docs/standards/durability-consistency.md`, `docs/standards/scalability-availability.md` |
| Scope | In repo (`lotus-core`) |

## Executive Summary

RFC 006 addressed correctness defects discovered by tests and strengthened integrity safeguards around:
1. Epoch-aware timeseries UPSERT semantics.
2. Outbox retry accounting robustness.
3. Test-harness stability for migration-sensitive test runs.

The requested fixes are implemented and covered by tests.

## Original Requested Requirements (Preserved)

RFC 006 originally targeted:
1. Prevent cross-epoch data corruption in timeseries persistence paths.
2. Fix outbox retry behavior when `retry_count` is `NULL`.
3. Add/strengthen unit and integration coverage for repaired integrity paths.
4. Improve deterministic test setup reliability under migration timing.

## Current Implementation Reality

Implemented outcomes:
1. Timeseries UPSERT conflict keys include `epoch`.
2. Outbox retry increment uses `coalesce(retry_count, 0) + 1`.
3. Integrity-focused tests exist for both areas.
4. Test fixture includes migration readiness wait behavior.

Evidence:
- `src/services/timeseries_generator_service/app/repositories/timeseries_repository.py`
- `src/libs/portfolio-common/portfolio_common/outbox_dispatcher.py`
- `tests/unit/services/timeseries_generator_service/timeseries-generator-service/repositories/test_unit_timeseries_repo.py`
- `tests/integration/libs/portfolio-common/test_outbox_dispatcher_delivery_results.py`
- `tests/conftest.py`

## Requirement-to-Implementation Traceability

| Original Requirement | Current Implementation | Evidence |
| --- | --- | --- |
| Epoch-safe timeseries write semantics | UPSERT uniqueness/merge logic keys include epoch | `timeseries_repository.py`; unit tests |
| Robust outbox retry increment from null | `coalesce` increment logic implemented | `outbox_dispatcher.py`; integration tests |
| Integrity regression coverage | Unit + integration tests for repaired paths | listed test files |
| Stable migration-aware test setup | Fixture-level migration wait/synchronization logic | `tests/conftest.py` |

## Design Reasoning and Trade-offs

1. **Why epoch in conflict keys**: stale epoch rows must never overwrite current-epoch results.
2. **Why defensive retry increment**: nullability in operational rows should not break retry pipelines.
3. **Why test-harness hardening**: false-negative failures from startup/migration races reduce signal quality.
4. **Trade-off**: slightly more explicit persistence logic and setup complexity for significantly stronger data safety.

## Gap Assessment

No unresolved critical integrity issue remains in RFC 006 scope.

## Deviations and Evolution Since Original RFC

1. Integrity checks are now part of broader operational readiness and signoff posture in later RFCs.
2. Additional reliability waves (query/pipeline coverage gates) build on this baseline rather than replace it.

## Proposed Changes

1. Keep RFC 006 as implemented data-integrity hardening baseline.
2. Continue carrying these assertions in regression suites and release checks.

## Test and Validation Evidence

1. Timeseries repository UPSERT behavior:
   - `tests/unit/services/timeseries_generator_service/timeseries-generator-service/repositories/test_unit_timeseries_repo.py`
2. Outbox retry-from-null behavior:
   - `tests/integration/libs/portfolio-common/test_outbox_dispatcher_delivery_results.py`
3. Additional persistence/timeseries safety checks:
   - `tests/unit/services/persistence_service/consumers/test_persistence_transaction_consumer.py`
   - `tests/unit/services/timeseries_generator_service/timeseries-generator-service/core/test_portfolio_timeseries_logic.py`

## Original Acceptance Criteria Alignment

Original acceptance intent is satisfied:
1. Cross-epoch overwrite risk in timeseries persistence is mitigated.
2. Outbox retry semantics are resilient for null prior state.
3. New/reinforced tests cover repaired paths.
4. Test environment reliability improvements are in place.

## Rollout and Backward Compatibility

Documentation retrofit only; no new runtime contract introduced.

## Open Questions

1. Should integrity-specific checks be surfaced as an explicit pre-merge/report artifact in addition to CI test pass/fail?

## Next Actions

1. Keep RFC 006 classification as `Fully implemented and aligned`.
2. Maintain regression coverage for epoch-keyed UPSERTs and outbox retry semantics.
