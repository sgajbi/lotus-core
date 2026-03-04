# RFC 028 - Strengthening Test Strategy with Multi-Layered Coverage

| Metadata | Value |
| --- | --- |
| Status | Partially Implemented |
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

Current implementation is partial:
1. Unit suites widely use real `TransactionEvent`/Pydantic models.
2. Core test infrastructure is stronger (manifest-driven suites, docker-backed fixtures).
3. But RFC-specific artifacts (testing strategy doc, incident coverage doc, dedicated consumer-integration layer with ephemeral broker fixtures) are not fully present.

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

Not yet implemented as RFC written:
1. No `docs/testing_strategy.md` present.
2. No `docs/incidents/incident_to_coverage.md` present.
3. No explicit consumer-level integration test layer with ephemeral Kafka fixture pattern in root fixtures.
4. No dedicated persistence consumer integration suite demonstrating consume-process-persist boundary loop.

Evidence:
- `tests/unit/services/calculators/cashflow_calculator_service/unit/core/test_cashflow_logic.py`
- `tests/unit/services/calculators/position_calculator/core/test_position_logic.py`
- `tests/unit/transaction_specs/test_buy_slice0_characterization.py`
- `tests/unit/transaction_specs/test_sell_slice0_characterization.py`
- `tests/conftest.py`
- `scripts/test_manifest.py`
- `.github/workflows/ci.yml`

## Requirement-to-Implementation Traceability

| Original Requirement | Current Implementation in lotus-core | Evidence |
| --- | --- | --- |
| Domain-valid event models in unit tests | Broadly implemented in major suites | unit tests listed above |
| Consumer-level integration layer with ephemeral broker | Not implemented as dedicated layer | `tests/conftest.py`; integration test layout |
| Testing strategy doc | Not implemented | docs scan |
| Incident-to-coverage mapping doc | Not implemented | docs scan |

## Design Reasoning and Trade-offs

1. Event-model usage in unit tests already improves schema-fidelity and reduces brittle mocks.
2. Existing docker-backed fixtures prioritize realism, but they are heavier than the RFC’s intended fast boundary layer.

Trade-off:
- Current approach improved quality, but missed the explicit middle-layer testing architecture and documentation discipline requested by RFC 028.

## Gap Assessment

Remaining deltas:
1. Add formal test architecture docs and incident traceability mapping.
2. Implement a lightweight consumer-boundary integration pattern (targeted, faster than full E2E).

## Deviations and Evolution Since Original RFC

1. CI/test-matrix maturity progressed via RFC 029/030 streams.
2. Execution emphasis shifted to practical suite coverage first, while the RFC’s documentation/process artifacts lagged.

## Proposed Changes

1. Keep classification as `Partially implemented (requires enhancement)`.
2. Implement missing docs and explicit consumer-level integration design as a focused follow-up.

## Test and Validation Evidence

1. Domain-event instantiation in unit suites (examples listed above).
2. CI matrix execution paths:
   - `.github/workflows/ci.yml`
   - `Makefile` / `scripts/test_manifest.py`

## Original Acceptance Criteria Alignment

Partially aligned:
1. Event-model usage direction mostly satisfied.
2. Consumer-level integration layer and required docs remain incomplete.

## Rollout and Backward Compatibility

No runtime change introduced by this documentation retrofit.

## Open Questions

1. Should consumer-boundary integration layer run with in-memory broker abstraction or containerized Kafka per suite for stronger fidelity?

## Next Actions

1. Track RFC-028 remaining artifacts and consumer-boundary layer in delta backlog.
2. Add docs and pilot one service boundary suite (persistence consumer) before scaling pattern repo-wide.
3. Keep status as `Partially Implemented` until RFC-028 deltas (`RFC-028-D01`, `RFC-028-D02`) are closed in `RFC-DELTA-BACKLOG`.
