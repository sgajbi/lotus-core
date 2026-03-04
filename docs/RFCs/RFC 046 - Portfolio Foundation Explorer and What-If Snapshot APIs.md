# RFC 046 - Portfolio Foundation Explorer and What-If Snapshot APIs

| Metadata | Value |
| --- | --- |
| Status | Partially Implemented |
| Created | 2026-02-24 |
| Last Updated | 2026-03-04 |
| Owners | `query-service` |
| Depends On | RFC 046A, RFC 058, core snapshot + simulation contracts |
| Scope | Explorer-grade portfolio read models and iterative what-if API surfaces |

## Executive Summary

This RFC proposes explorer-oriented and what-if-oriented query contracts.
Current lotus-core reality provides meaningful building blocks but not the full proposed shape:
1. Canonical portfolio/position/transaction read APIs exist.
2. Simulation session and projected endpoints exist.
3. Core snapshot supports baseline/simulation sectioned responses.
4. Dedicated “portfolio foundation explorer” read model APIs described in this RFC are not implemented as distinct endpoints/contracts.

Classification: `Partially implemented (requires enhancement)`.

## Original Requested Requirements (Preserved)

Original RFC requested:
1. Explorer APIs with portfolio state/composition/health read models.
2. First-class what-if snapshot projection contracts for iterative workflows.
3. Strong provenance/freshness semantics for frontend trust and orchestration.

## Current Implementation Reality

Implemented building blocks:
1. Portfolio, position, and transaction APIs provide foundational read access.
2. Simulation session lifecycle and projected outputs are implemented under `/simulation-sessions/...`.
3. Core snapshot endpoint supports simulation-aware sectioned responses suitable for integration consumers.

Not fully implemented:
1. No dedicated “Portfolio Foundation Explorer” endpoint family with curated explorer view models and explicit health/composition contracts as described.
2. Freshness/provenance semantics remain uneven across related endpoints.
3. Latency-budgeted explorer contract and explicit feature-flag rollout path are not codified in this RFC’s requested form.

Evidence:
- `src/services/query_service/app/main.py`
- `src/services/query_service/app/routers/portfolios.py`
- `src/services/query_service/app/routers/positions.py`
- `src/services/query_service/app/routers/transactions.py`
- `src/services/query_service/app/routers/simulation.py`
- `src/services/query_service/app/routers/integration.py`
- `src/services/query_service/app/services/simulation_service.py`

## Requirement-to-Implementation Traceability

| Original Requirement | Current Implementation in lotus-core | Evidence |
| --- | --- | --- |
| Explorer-specific read-model APIs | Partially implemented via generic canonical read endpoints; no dedicated explorer family | portfolio/position/transaction routers |
| What-if projection contract | Implemented through simulation sessions and core snapshot simulation mode | simulation router + integration snapshot |
| Consistent provenance/freshness semantics | Partially implemented; not uniformly expressed as RFC requests | snapshot/integration DTO and service behavior |

## Design Reasoning and Trade-offs

1. Existing canonical APIs and simulation contracts offer reusable primitives with lower duplication risk.
2. Deferring dedicated explorer composites avoids premature coupling to one UI view model.

Trade-off:
- Without dedicated explorer contracts, clients may compose multiple APIs and carry orchestration complexity.

## Gap Assessment

Remaining deltas:
1. Decide whether to implement explicit explorer endpoint family or formally adopt compositional pattern as final design.
2. Normalize freshness/provenance semantics across explorer-relevant endpoints.

## Deviations and Evolution Since Original RFC

1. Simulation-first contracts (RFC 046A, RFC 058) became the practical realization path for what-if use cases.
2. This RFC remains broad and partially superseded in structure by later, more concrete simulation/snapshot RFCs.

## Proposed Changes

1. Keep classification as `Partially implemented`.
2. Rebaseline this RFC to either:
   - dedicated explorer contract delivery plan, or
   - explicit supersession by RFC 046A/RFC 058 + canonical endpoint composition.

## Test and Validation Evidence

1. Simulation router/service tests:
   - `tests/integration/services/query_service/test_simulation_router_dependency.py`
   - `tests/unit/services/query_service/services/test_simulation_service.py`
2. Core snapshot and canonical read-route tests:
   - `tests/unit/services/query_service/routers/test_integration_router.py`

## Original Acceptance Criteria Alignment

Partially aligned.

## Rollout and Backward Compatibility

No runtime change introduced by this documentation retrofit.

## Open Questions

1. Should explorer contracts live in lotus-core as dedicated APIs, or in lotus-gateway composition layer using lotus-core primitives?

## Next Actions

1. Decide definitive ownership/pattern for explorer view models.
2. If in-core ownership is chosen, raise follow-on RFC with exact endpoint contracts and SLO targets.
