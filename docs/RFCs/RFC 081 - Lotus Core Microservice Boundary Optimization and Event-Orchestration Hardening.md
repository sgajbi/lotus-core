# RFC 081 - Lotus Core Microservice Boundary Optimization and Event-Orchestration Hardening

**Status**: In Progress  
**Date**: 2026-03-07  
**Owner**: lotus-core Architecture  
**Reviewers**: Platform Architecture, Data Engineering, QA, SRE  
**Approvers**: *TBD*

## 0. Executive Summary

This RFC defines a banking-grade service-boundary and event-orchestration hardening plan for `lotus-core`.

Current decomposition is directionally correct, but there are boundary and trigger risks that can affect correctness under scale:

- Stage readiness is sometimes inferred from eventual DB state rather than explicit orchestration events.
- Some services combine orchestration and execution responsibilities.
- Query service mixes core read APIs with control-plane and integration endpoints.

This RFC introduces a phased architecture update that preserves existing throughput strengths while improving deterministic sequencing, auditability, and operational safety.

## 1. Purpose and Goals

### 1.1 Primary goals

- Ensure each microservice has a clear bounded-context responsibility.
- Ensure the right services are triggered at the right time through explicit event contracts.
- Improve horizontal scalability and parallel processing without correctness regressions.
- Strengthen banking-grade guarantees for accuracy, consistency, and reliability.

### 1.2 Non-goals

- Rewriting core valuation/cost/cashflow logic algorithms.
- Replacing Kafka or Postgres platform primitives.
- Introducing speculative services without measurable benefit.

## 2. Current Architecture Snapshot

### 2.1 Implemented service set

- `ingestion_service`
- `persistence_service`
- `cost_calculator_service`
- `cashflow_calculator_service`
- `position_calculator`
- `position_valuation_calculator`
- `timeseries_generator_service`
- `query_service`

### 2.2 Strengths

- Good domain-level decomposition across ingestion, persistence, calculation, valuation, and query.
- Event-driven propagation and asynchronous scaling are already present.
- Outbox/idempotency patterns are broadly in place.

### 2.3 Key risks observed

- Pipeline stage dependencies are not uniformly represented as explicit gating events.
- Mixed orchestration/execution concerns in valuation and timeseries services.
- Query service has mixed runtime responsibilities (core read-plane + control-plane + integration shape APIs).

## 3. Domain Boundary Evaluation

## 3.1 Keep (no merge now)

The following boundaries remain valid and should stay independent:

- `ingestion_service` as write-ingress and schema/contract gateway.
- `persistence_service` as canonical persistence and completion-event emitter.
- `cost_calculator_service` as transaction cost and lot-state authority.
- `cashflow_calculator_service` as cashflow rule/classification authority.
- `position_calculator` as position state/materialization authority.

Reason: these domains have distinct scaling and failure profiles and are foundational to parallelized event execution.

## 3.2 Split (recommended)

### A. Split valuation orchestration from valuation execution

Current: `position_valuation_calculator` hosts consumers, scheduler, and reprocessing worker.

Target:

- `valuation_orchestrator_service`
- `valuation_worker_service`

Benefits:

- Independent scaling of scheduler/control vs compute workers.
- Reduced blast radius for orchestration incidents.
- Cleaner ownership for SLA management.

### B. Split timeseries generation from portfolio aggregation orchestration

Current: `timeseries_generator_service` includes position-timeseries consumer + portfolio aggregation consumer + scheduler.

Target:

- `position_timeseries_service`
- `portfolio_aggregation_service`

Benefits:

- Better throughput control for position-level vs portfolio-level workloads.
- Clearer retry and dead-letter semantics per domain.

### C. Split query control-plane from core query read-plane

Current: `query_service` includes core portfolio/position/transaction reads plus integration/capabilities/simulation/operations support endpoints.

Target:

- `query_core_service` (authoritative read APIs)
- `query_control_plane_service` (integration capabilities, policy/provenance diagnostics, operational support)

Benefits:

- Protects core read SLOs from control-plane workload spikes.
- Clear runtime security and scaling policies by responsibility.

## 3.3 Merge (not recommended now)

No immediate merge of core calculators is recommended.

- Merging cost+cashflow+position could reduce some sequencing complexity but would tightly couple independent compute domains and reduce scaling flexibility.
- Correct sequencing should be solved via explicit orchestration contracts, not forced service co-location.

## 3.4 Remove

- `demo_data_loader` must be treated as non-production bootstrap utility only.
- Production deployment profile should not include it.

## 3.5 Add (high-value missing capabilities)

### A. Workflow orchestration service (new)

Add `pipeline_orchestrator_service` to enforce stage gates and emit readiness transitions.

Responsibilities:

- Consume stage completion events.
- Maintain deterministic stage state per `(portfolio_id, date, epoch)` and `(portfolio_id, security_id, date, epoch)`.
- Emit explicit gate events (examples below).

### B. DLQ replay/remediation service (new)

Add `event_replay_service` for controlled replay with audit trails and guardrails.

### C. Reconciliation and controls service (new)

Add `financial_reconciliation_service` for independent controls:

- transaction-to-cashflow completeness
- position-to-valuation consistency
- day-level timeseries integrity

## 4. Event-Driven Trigger Hardening

## 4.1 Current trigger issue class

Some downstream calculations rely on "data likely available" assumptions rather than explicit readiness events.

Risk:

- race conditions under load
- temporary partial analytics states
- difficult root-cause analysis for intermittent correctness defects

## 4.2 Target trigger model

Introduce explicit gate events:

- `transaction_processing_completed` (cost + cashflow required signals attached)
- `portfolio_day_ready_for_valuation`
- `valuation_day_completed`
- `position_timeseries_day_completed`
- `portfolio_aggregation_day_completed`

Orchestrator enforces prerequisites before emitting next-stage events.

## 4.3 Stage state model

Create durable pipeline stage table (or equivalent state stream) keyed by:

- `portfolio_id`
- `security_id` (nullable for portfolio-level stages)
- `business_date`
- `epoch`

Track status:

- `PENDING`, `READY`, `RUNNING`, `COMPLETED`, `FAILED`, `REQUIRES_REPLAY`

## 5. Banking-Grade Reliability Controls

## 5.1 Correctness invariants

- Idempotent event processing at every state-mutating service.
- Exactly-once effect semantics via outbox + idempotency + deterministic keys.
- Explicit epoch-aware sequencing for reprocessing windows.
- Deterministic replay guarantees for backdated corrections.

## 5.2 Data integrity controls

- Dual-write prohibition (single writer per domain table family).
- Reconciliation controls service to detect drift early.
- Gating policy prevents downstream publication when upstream controls fail.

## 5.3 Throughput and scalability controls

- Consumer group autoscaling by lag and partition utilization.
- Partition key policy per domain:
  - transaction pipelines: `portfolio_id` (and where needed `portfolio_id+security_id` strategy)
  - valuation/time-series: date+portfolio scoped keys as required by ordering constraints

## 6. Implementation Plan (Phased)

## Phase 0 - Contracts and observability hardening (no topology change)

- Define canonical stage-gate event schemas.
- Add pipeline-stage audit table and metrics.
- Add readiness dashboards and alert policies.

Exit criteria:

- Every downstream trigger path has explicit prerequisite state checks.

## Phase 1 - Add orchestration service

- Introduce `pipeline_orchestrator_service`.
- Route existing completion events through stage coordinator.
- Emit gate events and remove implicit downstream assumptions.

Exit criteria:

- No downstream service starts a stage without orchestrator-issued readiness event.

## Phase 2 - Split valuation runtime

- Extract scheduler/reprocessing orchestration into `valuation_orchestrator_service`.
- Keep valuation compute in `valuation_worker_service`.

Exit criteria:

- Independent scaling of orchestrator and worker pools.

## Phase 3 - Split timeseries runtime

- Extract position and portfolio aggregation into separate services.
- Keep orchestration rules in orchestrator service.

Exit criteria:

- Portfolio aggregation no longer depends on implicit ordering side effects.

## Phase 4 - Split query control plane

- Move integration/capability/policy and support endpoints to `query_control_plane_service`.
- Preserve `query_core_service` SLO focus for critical reads.

Exit criteria:

- Core query latencies stable under control-plane load.

## 7. API and Event Contract Changes

- New event types and schema versions for stage gates.
- Backward-compatible consumer handling during migration window.
- Contract tests required for every gate event producer/consumer pair.

## 8. Migration and Rollout Strategy

- Use shadow mode for orchestrator first (observe-only, no gate enforcement).
- Enable gate enforcement by domain stage progressively:
  - transaction -> valuation
  - valuation -> timeseries
  - timeseries -> aggregation
- Keep rollback path via feature flags per stage gate.

## 9. Testing and Verification Strategy

## 9.1 Unit tests

- Orchestrator stage transitions and guard rules.
- Failure and retry semantics for gate emissions.

## 9.2 Integration tests

- End-to-end stage readiness transitions with forced delay/failure scenarios.
- Replay and epoch conflict handling.

## 9.3 E2E tests

- Full day lifecycle with transaction corrections and reprocessing.
- Parallel high-volume ingestion with deterministic final snapshots.

## 9.4 Non-functional tests

- Throughput/load tests for consumer lag and end-to-end latency.
- Chaos/failure injection for broker outage, DB lock contention, and partial service unavailability.

## 10. Acceptance Criteria

- Stage progression is fully event-gated and auditable.
- No known implicit trigger dependency remains in critical calculation path.
- SLOs maintained or improved under target volume.
- Financial reconciliation controls pass for production-like runs.

## 11. Risks and Mitigations

- Risk: migration complexity and temporary dual-path behavior.
  - Mitigation: phased rollout, feature flags, shadow mode, contract tests.

- Risk: event schema drift across services.
  - Mitigation: strict versioned contracts and CI schema compatibility checks.

- Risk: operational overhead of added services.
  - Mitigation: add only high-value services (orchestrator, replay, reconciliation) and defer speculative splits until volume thresholds.

## 12. Operational Runbook Updates

- Add stage-gate troubleshooting playbooks.
- Add DLQ replay governance SOP.
- Add reconciliation breach escalation workflow.

## 13. Open Questions

- Exact partition strategy standardization for high-cardinality portfolios.
- Whether orchestration state is DB-backed only or DB + compacted Kafka state topic.
- Final ownership between platform and domain teams for reconciliation controls.

## 14. Recommendation Summary

- **Merge**: none immediately.
- **Split**: valuation, timeseries, and query control-plane as phased targets.
- **Remove**: demo loader from production profile.
- **Add**: orchestrator service, replay service, reconciliation service.

The highest-priority change is explicit event-gate orchestration. It delivers the strongest correctness gain under scale while preserving the current domain decomposition strengths.

## 15. Implementation Progress (2026-03-07)

### 15.1 Delivered in this iteration (Phase 1 foundation)

- Added new `pipeline_orchestrator_service` runtime surface:
  - dual consumers for `processed_transactions_completed` and `cashflow_calculated`
  - durable outbox emission of `transaction_processing_completed`
  - service packaging, Docker image, compose integration, and Prometheus scrape target.
- Added durable stage-state model:
  - `pipeline_stage_state` table + Alembic migration
  - repository upsert/merge behavior for independent prerequisite signals
  - concurrency-safe claim transition to prevent duplicate readiness emission.
- Added explicit event contract:
  - `TransactionProcessingCompletedEvent` in canonical event model.
- Added quality coverage for stage gate behavior:
  - unit tests for orchestrator gate logic
  - integration tests for repository merge/idempotent-completion behavior.
- Routed position calculation trigger to orchestrator gate:
  - `position_calculator_service` now consumes `transaction_processing_completed`
  - consumer resolves canonical transaction from persistence by `transaction_id`
  - gate epoch is applied before position calculation for deterministic replay alignment.
  - replay compatibility retained by continuing to accept `processed_transactions_completed`
    for epoch-based reprocessing emissions.

### 15.2 Current scope boundary

- Implemented gate in this slice is `transaction_processing_completed` based on:
  - processed transaction signal present
  - cashflow signal present.
- Valuation-day and timeseries-day gate events remain in planned follow-on slices.

### 15.3 Remaining roadmap alignment

- Keep `portfolio_day_ready_for_valuation`, `valuation_day_completed`,
  `position_timeseries_day_completed`, and `portfolio_aggregation_day_completed`
  as next-stage gates for subsequent RFC-081 slices.
