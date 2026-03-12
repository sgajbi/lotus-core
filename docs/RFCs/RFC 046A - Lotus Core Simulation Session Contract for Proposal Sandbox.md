# RFC 046A - Lotus Core Simulation Session Contract for Proposal Sandbox

| Metadata | Value |
| --- | --- |
| Status | Implemented |
| Created | 2026-02-24 |
| Last Updated | 2026-03-04 |
| Owners | `query-service` simulation contracts |
| Depends On | RFC 013 evolution, RFC 058 snapshot integration |
| Scope | Session-based what-if workflow APIs without mutating committed portfolio records |

## Executive Summary

RFC 046A is implemented in lotus-core query-service:
1. Simulation session lifecycle endpoints exist.
2. Session change upsert/delete APIs exist with versioned updates.
3. Projected positions and projected summary endpoints are implemented.
4. Simulation state is stored in dedicated tables (`simulation_sessions`, `simulation_changes`) and separated from committed ledger transactions.

Classification: `Fully implemented and aligned`.

## Original Requested Requirements (Preserved)

Original RFC 046A requested:
1. Lifecycle APIs for create/get/close simulation sessions.
2. Session-scoped change ledger API.
3. Projection APIs for holdings and summary outcomes.
4. Non-booking isolation and deterministic behavior controls.

## Current Implementation Reality

Implemented:
1. Endpoints:
   - `POST /simulation-sessions`
   - `GET /simulation-sessions/{session_id}`
   - `DELETE /simulation-sessions/{session_id}`
   - `POST /simulation-sessions/{session_id}/changes`
   - `DELETE /simulation-sessions/{session_id}/changes/{change_id}`
   - `GET /simulation-sessions/{session_id}/projected-positions`
   - `GET /simulation-sessions/{session_id}/projected-summary`
2. Service layer enforces session active-state and applies deterministic change effects.
3. Repository layer persists session/change records and handles version increments/rollback behavior.
4. Database models for simulation entities are present in shared canonical models.
5. Unit and integration tests cover lifecycle, guardrails, and router status mappings.

Evidence:
- `src/services/query_control_plane_service/app/routers/simulation.py`
- `src/services/query_service/app/services/simulation_service.py`
- `src/services/query_service/app/repositories/simulation_repository.py`
- `src/services/query_service/app/dtos/simulation_dto.py`
- `src/libs/portfolio-common/portfolio_common/database_models.py`
- `tests/integration/services/query_service/test_simulation_router_dependency.py`
- `tests/unit/services/query_service/services/test_simulation_service.py`
- `tests/unit/services/query_service/repositories/test_simulation_repository.py`

## Requirement-to-Implementation Traceability

| Original Requirement | Current Implementation in lotus-core | Evidence |
| --- | --- | --- |
| Session lifecycle APIs | Implemented | simulation router + service |
| Session change APIs | Implemented | simulation router/service/repository |
| Projected positions/summary APIs | Implemented | simulation router + service |
| Non-booking isolation | Implemented via separate simulation tables and no transaction-ledger mutation path | database models + repository/service flows |

## Design Reasoning and Trade-offs

1. Session namespace cleanly separates exploratory what-if workflows from booking systems.
2. Versioned session updates support deterministic multi-step proposal editing.
3. Projection endpoints provide direct integration surface for UI/gateway loops.

Trade-off:
- Additional state lifecycle management (TTL/cleanup/retention) requires ongoing operations governance.

## Gap Assessment

No high-value implementation gap identified for RFC 046A baseline.

## Deviations and Evolution Since Original RFC

1. Core snapshot simulation mode (RFC 058 stream) complements session APIs and broadens integration options beyond standalone projected endpoints.

## Proposed Changes

1. Keep classification as `Fully implemented and aligned`.

## Test and Validation Evidence

1. Router integration tests:
   - `tests/integration/services/query_service/test_simulation_router_dependency.py`
2. Service logic unit tests:
   - `tests/unit/services/query_service/services/test_simulation_service.py`
3. Repository behavior unit tests:
   - `tests/unit/services/query_service/repositories/test_simulation_repository.py`

## Original Acceptance Criteria Alignment

Aligned.

## Rollout and Backward Compatibility

No runtime change introduced by this documentation retrofit.

## Open Questions

1. Should session retention/cleanup policy be formalized in a dedicated operations RFC as usage grows?

## Next Actions

1. Maintain simulation contract regression coverage and retention governance as adoption increases.
