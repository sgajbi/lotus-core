# RFC 013 - Digital Twin Simulation Engine

| Metadata | Value |
| --- | --- |
| Status | Partially Implemented |
| Created | 2025-08-30 |
| Last Updated | 2026-03-04 |
| Owners | lotus-core query-service simulation capability |
| Depends On | RFC 057, RFC 046A, RFC 058 (evolution path) |
| Related Standards | `docs/standards/data-model-ownership.md` |
| Scope | In repo (`lotus-core`) |

## Executive Summary

RFC 013 proposed a digital-twin simulation capability with asynchronous job orchestration and a separate `simulation-service`.
Lotus-core now has a substantial simulation capability implemented, but via a different architecture:
1. simulation session APIs live directly in query-service (`/simulation-sessions/*`)
2. simulation state is persisted in `simulation_sessions` and `simulation_changes`
3. projected positions/summary are computed on-demand synchronously.

So the business intent is implemented in part, while the original architectural form is superseded.

## Original Requested Requirements (Preserved)

Original RFC 013 requested:
1. A digital twin feature for hypothetical trades/cashflows before execution.
2. Async initiation endpoint (`POST /portfolios/{id}/simulations`) and job polling endpoint.
3. Dedicated `simulation-service` microservice.
4. Persisted job/result model (`simulation_jobs`, `simulation_results`).
5. “Before/after diff” outputs for allocation, concentration, and risk analytics.

## Current Implementation Reality

Implemented capability in lotus-core:
1. Simulation session lifecycle APIs:
   - create/get/close session
   - add/delete changes
   - projected positions and projected summary
2. Persistence layer for simulation sessions and changes.
3. Query-service simulation service/repository stack with integration and unit tests.

Not implemented as originally written:
1. No dedicated standalone `simulation-service` process.
2. No async job queue pattern for simulations.
3. No `simulation_jobs`/`simulation_results` tables as originally named.
4. No in-core concentration/risk diff report generation from this RFC's proposed schema.

Evidence:
- `src/services/query_service/app/routers/simulation.py`
- `src/services/query_service/app/services/simulation_service.py`
- `src/services/query_service/app/repositories/simulation_repository.py`
- `src/services/query_service/app/dtos/simulation_dto.py`
- `src/libs/portfolio-common/portfolio_common/database_models.py` (`SimulationSession`, `SimulationChange`)
- `alembic/versions/e3f4a5b6c7d8_feat_add_simulation_sessions_and_changes_tables.py`
- `tests/integration/services/query_service/test_simulation_router_dependency.py`
- `tests/unit/services/query_service/services/test_simulation_service.py`
- `tests/unit/services/query_service/repositories/test_simulation_repository.py`

## Requirement-to-Implementation Traceability

| Original Requirement | Current Implementation | Status | Evidence |
| --- | --- | --- | --- |
| Digital twin capability for hypothetical changes | Implemented via session + change model | Implemented | simulation router/service/repo |
| Async simulation jobs (`/simulations`, `/simulation-jobs`) | Not implemented in current form | Gap/superseded | no such routes |
| Separate `simulation-service` | Not implemented | Superseded | query-service in-process implementation |
| Persisted simulation workflow state | Implemented, but as session/change tables | Implemented (variant) | DB models + migration |
| Full before/after allocation/concentration/risk diff | Partially implemented (projected positions/summary only) | Partial | simulation service DTO outputs |

## Design Reasoning and Trade-offs

1. **Why current approach**: in-process query-service simulation sessions reduce operational complexity and integrate cleanly with canonical core data paths.
2. **Why no async job service currently**: current projected-state use cases are covered by synchronous session-driven APIs.
3. **Trade-off**: simpler architecture but narrower analytical output than original rich diff vision.

## Gap Assessment

RFC 013 is partially implemented:
1. Core simulation session capability exists and is production-aligned with newer RFCs.
2. Original async job-based architecture and broader analytics-diff outputs were not implemented in this RFC form.

## Deviations and Evolution Since Original RFC

1. Simulation design evolved through later RFCs (notably RFC 046A and RFC 058) toward session-centric contracts.
2. Ownership decomposition under RFC 057 preserved simulation as core capability while removing unrelated legacy analytics surfaces.
3. Some originally proposed downstream analytics sections (concentration/risk) moved to other domain owners.

## Proposed Changes

1. Keep RFC 013 as partially implemented historical baseline.
2. Treat RFC 046A and RFC 058 as authoritative evolution path for simulation contracts.
3. Do not pursue original separate microservice/job-table design unless a new scale/latency requirement justifies it.

## Test and Validation Evidence

1. Simulation router integration behavior:
   - `tests/integration/services/query_service/test_simulation_router_dependency.py`
2. Simulation service unit coverage:
   - `tests/unit/services/query_service/services/test_simulation_service.py`
3. Simulation repository unit coverage:
   - `tests/unit/services/query_service/repositories/test_simulation_repository.py`

## Original Acceptance Criteria Alignment

Alignment status:
1. Digital twin workflow capability: largely achieved (session model).
2. Async job service and endpoints: not achieved (superseded by alternate architecture).
3. Dedicated simulation microservice: not achieved (superseded).
4. Persisted simulation state: achieved (with different schema model).
5. Full analytics diff breadth from original proposal: partially achieved.

## Rollout and Backward Compatibility

No runtime change from this documentation retrofit.

## Open Questions

1. Should future simulation evolution add optional async execution mode for high-cost scenarios while preserving current session contracts?

## Next Actions

1. Keep RFC 013 classification as `Partially implemented (requires enhancement)`.
2. Track future simulation breadth changes through RFC 046A/RFC 058 follow-on work instead of resurrecting the original microservice plan by default.
