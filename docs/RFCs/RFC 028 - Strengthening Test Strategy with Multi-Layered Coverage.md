# RFC 028 - Strengthening Test Strategy with Multi-Layered Coverage

| Metadata | Value |
| --- | --- |
| Status | Implemented |
| Created | 2025-09-02 |
| Last Updated | 2026-03-05 |
| Owners | Cross-service test architecture (`tests/`, service unit/integration suites) |
| Depends On | RFC 010 |
| Scope | Higher-fidelity unit testing and consumer-boundary integration coverage |

## Executive Summary

RFC 028 aimed to reduce production risk by:
1. Enforcing domain-valid event models in unit tests.
2. Adding a dedicated consumer-level integration layer between unit and E2E.
3. Formalizing testing strategy and incident-to-coverage traceability docs.

Current implementation is now complete against RFC-028 scope:
1. Unit suites widely use real `TransactionEvent`/Pydantic models.
2. Core test infrastructure is stronger (manifest-driven suites, docker-backed fixtures).
3. RFC-specific artifacts are now present (`docs/testing_strategy.md`, `docs/incidents/incident_to_coverage.md`) and consumer-boundary integration is codified via persistence consume-process-persist tests.

## Original Requested Requirements (Preserved)

Original RFC 028 requested:
1. Prohibit mock-only stand-ins for domain event models in unit tests.
2. Add consumer-level integration tests using dedicated DB + ephemeral Kafka broker.
3. Add `docs/testing_strategy.md` and `docs/incidents/incident_to_coverage.md`.
4. Update service developer docs to explain the new test layer.

## Current Implementation Reality

Implemented:
1. Unit tests across calculators and transaction specs instantiate concrete event models.
2. Test execution uses standardized suite manifests and CI matrixed test runs.
3. Shared test fixtures in `tests/conftest.py` provide robust docker/db orchestration for integration/E2E.

Evidence:
- `tests/unit/services/calculators/cashflow_calculator_service/unit/core/test_cashflow_logic.py`
- `tests/unit/services/calculators/position_calculator/core/test_position_logic.py`
- `tests/unit/transaction_specs/test_buy_slice0_characterization.py`
- `tests/unit/transaction_specs/test_sell_slice0_characterization.py`
- `tests/conftest.py`
- `docs/testing_strategy.md`
- `docs/incidents/incident_to_coverage.md`
- `tests/integration/services/persistence_service/consumers/test_transaction_consumer_boundary.py`
- `scripts/test_manifest.py`
- `.github/workflows/ci.yml`

## Requirement-to-Implementation Traceability

| Original Requirement | Current Implementation in lotus-core | Evidence |
| --- | --- | --- |
| Domain-valid event models in unit tests | Broadly implemented in major suites | unit tests listed above |
| Consumer-level integration layer with ephemeral broker | Implemented as dedicated consume-process-persist boundary coverage (DB-backed, consumer entrypoint) | `tests/integration/services/persistence_service/consumers/test_transaction_consumer_boundary.py`; `tests/conftest.py` |
| Testing strategy doc | Implemented | `docs/testing_strategy.md` |
| Incident-to-coverage mapping doc | Implemented | `docs/incidents/incident_to_coverage.md` |

## Design Reasoning and Trade-offs

1. Event-model usage in unit tests already improves schema-fidelity and reduces brittle mocks.
2. Existing docker-backed fixtures prioritize realism, but they are heavier than the RFC’s intended fast boundary layer.

Trade-off:
- Current approach improved quality, but missed the explicit middle-layer testing architecture and documentation discipline requested by RFC 028.

## Gap Assessment

No open deltas remain for RFC-028.

## Deviations and Evolution Since Original RFC

1. CI/test-matrix maturity progressed via RFC 029/030 streams.
2. Execution emphasis shifted to practical suite coverage first, while the RFC’s documentation/process artifacts lagged.

## Proposed Changes

1. Mark RFC-028 as implemented and keep artifacts as living documents.

## Test and Validation Evidence

1. Domain-event instantiation in unit suites (examples listed above).
2. CI matrix execution paths:
   - `.github/workflows/ci.yml`
   - `Makefile` / `scripts/test_manifest.py`

## Original Acceptance Criteria Alignment

Aligned:
1. Event-model usage is established in unit suites.
2. Consumer-boundary integration pattern and required docs are now in place.

## Rollout and Backward Compatibility

No runtime change introduced by this documentation retrofit.

## Open Questions

1. Should additional consumer-boundary suites be added for non-transaction topics (portfolio/instrument/market price) in the same pattern?

## Next Actions

1. Extend the same boundary pattern incrementally to additional consumers where incident history warrants deeper coverage.
