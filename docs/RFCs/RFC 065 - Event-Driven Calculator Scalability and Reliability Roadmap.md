# RFC 065 - Event-Driven Calculator Scalability and Reliability Roadmap

| Field | Value |
| --- | --- |
| Status | Implemented |
| Created | 2026-03-03 |
| Last Updated | 2026-03-04 |
| Owners | lotus-core platform execution owners |
| Depends On | foundational ingestion/calculator event contracts |
| Related Standards | operational SLO and API-first ops standards; RFC-066 readiness layer |
| Scope | In repo |

## Executive Summary
RFC 065 defines and executes the calculator scalability/reliability roadmap for event-driven processing at institutional loads. Implementation evidence includes partitioning hardening, replay safety controls, ingestion operations observability expansion, policy introspection APIs, CI/automation gates, and runbook support.

RFC 065 is implemented and serves as the operational backbone for RFC 066 readiness gates.

## Original Requested Requirements (Preserved)
1. Scale calculators independently with deterministic ordering where financially required.
2. Harden idempotency, replay safety, and failure isolation.
3. Provide backlog/lag/capacity observability with explicit operating signals.
4. Add phased delivery with measurable acceptance criteria.
5. Publish runbook-usable policy and operational diagnostics.

## Current Implementation Reality
1. Ingestion partition-key hardening and deterministic replay ordering implemented.
2. Consumer tuning and scaling controls implemented (config + KEDA artifacts).
3. DLQ taxonomy, replay guardrails, and durable replay audit behaviors implemented.
4. Ingestion operations APIs now expose rich health, backlog, policy, capacity, replay diagnostics, and queue health contracts.
5. CI includes ops-contract suites and complementary readiness gate jobs.

## Requirement-to-Implementation Traceability
| Requirement | Current State | Evidence |
| --- | --- | --- |
| Deterministic ordering/partition hardening | Implemented | `src/services/ingestion_service/app/services/ingestion_service.py`; replay/order logic and related tests |
| Idempotency/replay safety and blast-radius guardrails | Implemented | `src/services/ingestion_service/app/routers/ingestion_jobs.py`; replay guardrail tests |
| DLQ reason-code taxonomy and diagnostics | Implemented | base consumer + ingestion ops DTO/service/router updates |
| Capacity/backlog/operating-band policy APIs | Implemented | ingestion ops endpoints (`/ingestion/health/*`) and service logic |
| Operational policy introspection | Implemented | `/ingestion/health/policy` endpoint and tests |
| Runbook and operations guidance | Implemented | `docs/operations/RFC-065-Calculator-Scalability-Operations-Playbook.md` |

## Design Reasoning and Trade-offs
1. Event-driven scaling with strict key-ordering at critical boundaries preserves financial correctness while enabling parallelism.
2. Exposing policy and saturation signals via API avoids DB-first operational dependence.
3. Trade-off: more ops endpoints and policy metadata require ongoing contract governance and test discipline.

## Gap Assessment
1. No material blocking gap found for RFC-065 baseline outcomes.
2. Ongoing threshold tuning remains operational, not architectural.

## Deviations and Evolution Since Original RFC
1. RFC includes rich execution log detail; this standardized form retains intent while mapping outcomes clearly to evidence categories.
2. Institutional extension items in this RFC are now complemented by RFC-066 gating layers.

## Proposed Changes
1. Keep RFC 065 as implemented roadmap record.
2. Use RFC 066 and subsequent runbooks for ongoing readiness enforcement/tuning.

## Test and Validation Evidence
1. `src/services/ingestion_service/app/routers/ingestion_jobs.py`
2. `src/services/ingestion_service/app/services/ingestion_job_service.py`
3. `tests/integration/services/ingestion_service/test_ingestion_routers.py`
4. `tests/unit/services/ingestion_service/services/test_ingestion_job_service_*`
5. `docs/operations/RFC-065-Calculator-Scalability-Operations-Playbook.md`

## Original Acceptance Criteria Alignment
1. Scalable and deterministic event-driven operations model: aligned.
2. Replay/failure isolation controls: aligned.
3. Operational observability and policy contracts: aligned.

## Rollout and Backward Compatibility
1. Improvements are additive/hardening-oriented across ingestion and operations surfaces.
2. Existing workflows remain while operational controls become stricter and more explicit.

## Open Questions
1. Should operating-band thresholds become centrally managed platform policy artifacts for cross-app consistency?

## Next Actions
1. Continue threshold calibration based on production-like load artifacts.
2. Keep ops-contract and readiness gate suites mandatory in CI.
