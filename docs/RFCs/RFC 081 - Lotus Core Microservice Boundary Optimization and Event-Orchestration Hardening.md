# RFC 081 - Lotus Core Microservice Boundary Optimization and Event-Orchestration Hardening

**Status**: Implemented  
**Date**: 2026-03-08  
**Owner**: lotus-core Architecture  
**Reviewers**: Platform Architecture, Data Engineering, QA, SRE  
**Approvers**: *TBD*

## 0. Executive Summary

This RFC defines a banking-grade service-boundary and event-orchestration hardening plan for `lotus-core`.

Current decomposition is directionally correct, but there are boundary and trigger risks that can affect correctness under scale:

- Stage readiness is sometimes inferred from eventual DB state rather than explicit orchestration events.
- Some services combine orchestration and execution responsibilities.
- Query service mixes core read APIs with control-plane and integration endpoints.
- Replay/remediation and RFC-065 operational diagnostics remain coupled to write ingress.

This RFC introduces a phased architecture update that preserves existing throughput strengths while improving deterministic sequencing, auditability, and operational safety.

## 0.1 Implementation status snapshot

Implemented under RFC 081 as of 2026-03-08:

- `valuation_orchestrator_service` split from valuation compute runtime
- `portfolio_aggregation_service` split from position-timeseries worker runtime
- `query_control_plane_service` split from core query read-plane
- `event_replay_service` split from ingestion write ingress
- `financial_reconciliation_service` added as the independent controls plane
- automatic post-aggregation reconciliation trigger path:
  `portfolio_aggregation_day_completed -> pipeline_orchestrator_service -> financial_reconciliation_requested -> financial_reconciliation_service`
- automatic reconciliation outcome hardening path:
  `financial_reconciliation_completed -> pipeline_orchestrator_service -> portfolio_day_controls_evaluated`
- explicit control policy decisioning on the orchestrator-owned controls event:
  blocking outcomes now set `controls_blocking=true` and `publish_allowed=false`
  for the affected `(portfolio_id, business_date, epoch)` scope
- support/control-plane visibility of the latest portfolio-day controls state
  through support overview APIs

RFC 081 architectural scope is implemented. Remaining work, if any, should now be treated
as normal follow-on product hardening or additional control-policy consumers, not as open
boundary-decomposition scope under this RFC.

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
- `portfolio_aggregation_service`
- `pipeline_orchestrator_service`
- `valuation_orchestrator_service`
- `query_control_plane_service`
- `event_replay_service`
- `financial_reconciliation_service`
- `query_service`

### 2.2 Strengths

- Good domain-level decomposition across ingestion, persistence, calculation, valuation, and query.
- Event-driven propagation and asynchronous scaling are already present.
- Outbox/idempotency patterns are broadly in place.

### 2.3 Key risks observed

- Pipeline stage dependencies are not uniformly represented as explicit gating events.
- Mixed orchestration/execution concerns in valuation and timeseries services.
- Query service has mixed runtime responsibilities (core read-plane + control-plane + integration shape APIs).
- Ingestion write ingress and replay/remediation controls can scale and fail differently.

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
- durable run/finding audit tables with rerunnable scoped checks
- RFC-065 grade health, metrics, and operational contract surfaces
- event-driven automatic control invocation after portfolio aggregation completes
- deterministic run dedupe for replay-safe automatic controls

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
- `financial_reconciliation_requested`
- `financial_reconciliation_completed`
- `portfolio_day_controls_evaluated`

Orchestrator enforces prerequisites before emitting next-stage events.

## 4.3 Stage state model

Create durable pipeline stage table (or equivalent state stream) keyed by:

- `portfolio_id`
- `security_id` (nullable for portfolio-level stages)
- `business_date`
- `epoch`

Track status:

- `PENDING`, `READY`, `RUNNING`, `COMPLETED`, `FAILED`, `REQUIRES_REPLAY`

Automatic reconciliation requests are emitted only after the portfolio aggregation stage reaches `COMPLETED`
for the relevant `(portfolio_id, business_date, epoch)` key.
Automatic reconciliation outcomes are then recorded as a portfolio-day control stage with monotonic status semantics:
`COMPLETED`, `REQUIRES_REPLAY`, or `FAILED`.

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

## Phase 5 - Split replay and controls planes

- Extract replay/remediation operations out of `ingestion_service` into `event_replay_service`.
- Add `financial_reconciliation_service` for independent controls and integrity checks.
- Route post-aggregation control execution through orchestrator-issued events rather than manual-only invocation.

Exit criteria:

- Ingestion runtime remains focused on canonical write ingress.
- Replay/remediation and controls operate as independent control planes with RFC-065 runtime standards.
- Automatic post-aggregation reconciliation is replay-safe and idempotent.

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
  - explicit collision guard to reject cross-portfolio key reuse
    for `(stage_name, transaction_id, epoch)` before state mutation.
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
- Added valuation-readiness trigger path:
  - orchestrator emits `portfolio_day_ready_for_valuation` alongside transaction completion
  - valuation service consumes readiness events and idempotently upserts valuation jobs.
- Added valuation completion gate path:
  - valuation service emits `valuation_day_completed` after valuation snapshot persistence
  - timeseries service consumes `valuation_day_completed` as canonical trigger while
    retaining `daily_position_snapshot_persisted` compatibility.
- Added timeseries completion gate path:
  - timeseries service emits `position_timeseries_day_completed` after position-timeseries persistence
  - timeseries service emits `portfolio_aggregation_day_completed` after portfolio aggregation completion
  - outbox dispatcher is now active in timeseries runtime for durable gate publication.

### 15.4 Race-condition safeguards applied in this slice

- Stage completion emission remains single-claim via conditional transition
  (`mark_stage_completed_if_pending`), preventing duplicate readiness publication.
- Stage-state repository rejects cross-portfolio collision on shared
  `(stage_name, transaction_id, epoch)` keys to avoid silent cross-talk.
- Consumer idempotency (`processed_events`) is enforced before any state mutation
  in orchestrator and valuation-readiness consumers.
- Valuation readiness job creation is race-safe via `upsert_job` with
  `ON CONFLICT DO UPDATE`, making duplicate readiness signals harmless.
- Cashflow rule-cache refresh path now uses an async lock around stale/miss refresh
  to prevent concurrent duplicate database loads under burst traffic.
- Cashflow runtime now fails fast when any critical task exits unexpectedly
  (consumer, outbox dispatcher, or web server), preventing silent partial-outage mode.

### 15.5 Delivered in subsequent RFC 081 slices (2026-03-08)

- Split valuation orchestration from compute execution:
  - `valuation_orchestrator_service` owns scheduling and orchestration concerns.
  - `position_valuation_calculator` remains the compute/runtime worker.
- Split portfolio aggregation from the position-timeseries worker:
  - `timeseries_generator_service` now owns position-timeseries computation only.
  - `portfolio_aggregation_service` owns portfolio aggregation scheduling and computation.
- Split query control-plane from the core read-plane:
  - `query_service` remains focused on authoritative read APIs.
  - `query_control_plane_service` owns integration, simulation, and operations-facing support APIs.
- Split replay/remediation from ingestion write ingress:
  - `event_replay_service` now owns replay, DLQ recovery, and RFC-065 diagnostics.
- Added independent controls plane:
  - `financial_reconciliation_service` owns durable reconciliation runs/findings,
    control APIs, and automatic event-driven bundle execution.

### 15.6 Automatic reconciliation trigger path (implemented)

Implemented trigger chain:

1. `portfolio_aggregation_service` emits `portfolio_aggregation_day_completed`.
2. `pipeline_orchestrator_service` consumes that event and publishes
   `financial_reconciliation_requested` through the outbox.
3. `financial_reconciliation_service` consumes the request and runs:
   - `transaction_cashflow`
   - `position_valuation`
   - `timeseries_integrity`
4. Automatic runs use deterministic dedupe keys:
   `auto:{reconciliation_type}:{portfolio_id}:{business_date}:{epoch}`
5. Duplicate event delivery or replay reuses the existing reconciliation run
   instead of creating duplicate control records.

Design rationale:

- The orchestrator owns stage progression, so it owns post-stage control triggering.
- The reconciliation service stays blind to source-delivery mode and only applies
  durable idempotency plus control computation.
- Persisted dedupe keys remove dependence on process-local memory and protect
  against race conditions under replay or concurrent duplicate delivery.

Validation completed for this slice:

- unit tests for orchestrator emission, automatic bundle execution,
  dedupe-key generation, and reconciliation event consumption
- static validation via `ruff` and `py_compile`

### 15.7 Reconciliation outcome gating and race-hardening (implemented)

Implemented additions:

1. `financial_reconciliation_service` now emits `financial_reconciliation_completed`
   after the automatic bundle finishes.
2. Bundle outcome is deterministic:
   - `FAILED` if any reconciliation run fails terminally
   - `REQUIRES_REPLAY` if runs complete but any `ERROR` findings remain
   - `COMPLETED` if all runs complete without blocking findings
3. `pipeline_orchestrator_service` consumes that completion event, upserts the
   `FINANCIAL_RECONCILIATION` portfolio-day control stage, and emits
   `portfolio_day_controls_evaluated`.
4. Portfolio-day control stage status merges monotonically:
   a duplicate or late event may preserve or worsen the current status but never
   downgrade `REQUIRES_REPLAY` or `FAILED` back to `COMPLETED`.
5. The emitted controls event now carries explicit policy semantics:
   - `controls_blocking=true` and `publish_allowed=false` for `FAILED` or
     `REQUIRES_REPLAY`
   - `controls_blocking=false` and `publish_allowed=true` only for `COMPLETED`
6. `query_control_plane_service` support overview now surfaces the latest
   portfolio-day control status, epoch, and publish decision so operational
   tooling cannot silently treat a blocked day as healthy.

Race-condition and replay safeguards:

- reconciliation bundle runs remain deduped per
  `auto:{reconciliation_type}:{portfolio_id}:{business_date}:{epoch}`
- completion publication is written through the outbox in the same DB transaction
  as event-consumer idempotency
- orchestrator control-stage updates use a deterministic synthetic stage key
  per portfolio-day scope
- status merge is severity-aware, preventing stale replay from erasing a blocking state

Testing completed for this slice:

- reconciliation outcome classification unit coverage
- reconciliation completion consumer unit coverage
- financial reconciliation runtime supervision coverage
- pipeline orchestrator runtime supervision coverage updated for the new consumer
- full `unit` manifest passed locally
- Cashflow service startup now enforces a single outbox-dispatcher owner
  (`ConsumerManager`) to prevent duplicate dispatch loops on the same outbox table.
- Pipeline orchestrator runtime now applies the same fail-fast supervision model,
  ensuring consumer/dispatcher/web task crashes trigger deterministic service shutdown
  instead of silent degraded processing.
- Position valuation runtime now applies fail-fast supervision across
  consumers, outbox dispatcher, valuation scheduler, reprocessing worker,
  and web server tasks to prevent silent partial-outage operation.
- Timeseries runtime now applies fail-fast supervision across
  timeseries consumers, aggregation scheduler, outbox dispatcher,
  and web server tasks to enforce deterministic shutdown on critical task failure.
- Persistence runtime now applies fail-fast supervision across
  domain consumers, outbox dispatcher, and web server tasks, eliminating
  silent degraded processing when a critical runtime task exits unexpectedly.
- Position calculation runtime now applies fail-fast supervision for
  gated/replay consumers, outbox dispatcher, and web server tasks.
- Cost calculation runtime now applies fail-fast supervision for
  core/reprocessing consumers, outbox dispatcher, and web server tasks.
- Runtime supervision logic is now centralized in shared
  `portfolio_common.runtime_supervision.wait_for_shutdown_or_task_failure`,
  removing duplicated lifecycle logic across service managers and reducing
  maintenance and drift risk.
- Phase 2 valuation split delivered:
  - added `valuation_orchestrator_service` for valuation readiness ingestion,
    market-price reprocessing triggers, scheduler dispatch, and reprocessing worker loops.
  - narrowed `position_valuation_calculator` to worker-only valuation compute
    (`valuation_required` consumer + outbox publication).
  - updated container topology and observability wiring for the new service.
- Phase 3 timeseries split delivered:
  - narrowed `timeseries_generator_service` to position-timeseries worker-only
    processing (`daily_position_snapshot_persisted` and `valuation_day_completed`
    consumers + position completion publication).
  - added `portfolio_aggregation_service` for aggregation job scheduling,
    `portfolio_aggregation_required` consumption, portfolio-timeseries persistence,
    and completion publication.
  - removed duplicate in-process scheduler/dispatcher startup from
    `timeseries_generator_service/app/main.py`, ensuring a single runtime owner
    for background loops.
- Phase 4 query split delivered:
  - narrowed `query_service` to core read-plane endpoints only
    (portfolio, position, transaction, market-data, and lookup APIs).
  - added `query_control_plane_service` for integration contracts,
    analytics export/input APIs, operational diagnostics, and simulation workflows.
  - updated container topology and observability wiring to run the control plane
    independently from the core read plane.
- Replay control-plane split delivered:
  - narrowed `ingestion_service` to canonical write ingress, upload adapters,
    and reprocessing request submission.
  - added `event_replay_service` for ingestion job inspection, retry control,
    consumer DLQ replay, replay audit access, operations mode control, and
    RFC-065 operational diagnostics (`/ingestion/health/*`, policy, capacity,
    backlog, and idempotency endpoints).
  - preserved durable replay audit, deterministic replay fingerprinting, and
    control-plane guardrails while moving the runtime to its own independently
    scalable service boundary.
  - aligned the new service with RFC 065 operational standards:
    dedicated health/readiness probes, Prometheus exposure, Docker/runtime
    topology, smoke/load/recovery automation coverage, and protected ops-token
    contracts.

### 15.2 Current scope boundary

- Implemented gates in this slice are:
  - `transaction_processing_completed` based on:
  - processed transaction signal present
  - cashflow signal present.
  - `portfolio_day_ready_for_valuation` for security-scoped stage completions.
- `valuation_day_completed` from valuation to timeseries is now implemented.
- `position_timeseries_day_completed` and `portfolio_aggregation_day_completed`
  are now implemented.

### 15.3 Remaining roadmap alignment

- RFC 081 roadmap scope is complete.
- Any further work should be tracked as:
  - incremental operational hardening against the now-stable service topology
  - new business-domain RFCs that consume the explicit control-plane contracts
  - independent reliability or observability enhancements under active runbooks

## 16. Closure Evidence (2026-03-08)

RFC 081 is closed as implemented based on merged code, runtime topology alignment,
and main-grade validation evidence on `main` commit
`7313191ac7bcbe8f2150fcb7164f9aa138c9acc5`.

Implemented service-boundary outcomes:

- `valuation_orchestrator_service` split from valuation compute execution
- `portfolio_aggregation_service` split from position-timeseries execution
- `query_control_plane_service` split from core query read-plane ownership
- `event_replay_service` split from ingestion write-ingress ownership
- `financial_reconciliation_service` established as an independent controls plane
- orchestrator-owned `portfolio_day_controls_evaluated` event introduced as the
  canonical portfolio-day control decision surface

Validation evidence:

- PR-quality gates passed before merge, including:
  - lint, typecheck, unit, unit-db, integration-lite, contract suites,
    docker smoke, latency gate, fast performance gate, and coverage gate
- Push-to-main runtime validation on run `22816299659` cleared the following on
  the RFC 081 merge commit:
  - `Lint, Typecheck, Unit Tests`
  - `Tests (unit)`
  - `Tests (unit-db)`
  - `Tests (integration-lite)`
  - `Tests (ops-contract)`
  - `Validate Docker Build`
  - `Docker Smoke Contract`
  - `Latency Gate`
  - `Performance Load Gate (Fast)`
  - `Performance Load Gate (Full)`
  - `E2E Smoke`
- Targeted local validation during the final closure pass also passed for the
  final control-policy path:
  - targeted unit coverage for `pipeline_orchestrator_service`,
    `financial_reconciliation_service`, and `query_service`
  - DB-backed integration for `pipeline_stage_repository`
  - targeted E2E coverage for `test_complex_portfolio_lifecycle.py`

Closure assessment:

- No open architectural decomposition delta remains under RFC 081.
- Documentation, runtime topology, orchestration policy, and test coverage are
  aligned with the implemented service model.
- The remaining `Failure Recovery Gate` in the active push-to-main run is a
  release-grade runtime assurance gate, not an architectural completion blocker
  for this RFC.
