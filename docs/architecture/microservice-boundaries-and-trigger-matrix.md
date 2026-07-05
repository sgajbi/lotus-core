# Lotus Core Microservice Boundaries and Trigger Matrix

Last updated: 2026-07-05
Source authority: RFC 081

Runtime-boundary governance: this matrix documents current-state service responsibilities. It is
not approval evidence for new deployable splits. New or expanded deployable boundaries must follow
`docs/standards/runtime-boundary-decision-standard.md` and be cataloged in
`docs/architecture/runtime-boundary-decision-catalog.json`.

Related boundary records:

1. Architecture map: `docs/architecture.md`
2. Target architecture: `docs/architecture/lotus-core-target-architecture.md`
3. Runtime-boundary decision standard: `docs/standards/runtime-boundary-decision-standard.md`
4. Runtime-boundary decision catalog: `docs/architecture/runtime-boundary-decision-catalog.json`
5. In-process modularity standard: `docs/standards/in-process-modularity-package-standard.md`
6. In-process boundary contract: `docs/standards/in-process-boundary-contract-standard.md`

## How To Read This Matrix

Use this page in this order:

1. identify the current deployable and its event/API triggers,
2. identify the in-process boundary that should be strengthened first,
3. check whether the runtime split is only historical/current-state or has current evidence,
4. require a runtime-boundary decision record before adding a new deployable, worker, scheduler, or
   separately operated service boundary.

The default pattern is `no split yet`: important modules should become clear packages,
application services, domain policies, ports, adapters, or proof builders inside the current
deployable until scale, deployment cadence, operations ownership, persistence ownership, failure
isolation, security, or SLO evidence proves a runtime boundary is needed.

## Design-Before-Runtime Boundary Matrix

| Deployable | In-Process Bounded Context | Package Boundary To Strengthen First | Application Owner | Ports, Adapters, Proof, And Contract Artifacts | Runtime Split Posture |
| --- | --- | --- | --- | --- | --- |
| `ingestion_service` | Source-data write ingress, upload validation, ingestion job lifecycle, idempotency, and replay audit. | `app/domain`, `app/application`, `app/ports`, `app/infrastructure`, `app/routers`; legacy `DTOs`, `services`, `transformers`, and `producers` remain migration scope. | Ingestion use cases and workflow policies. | Upload publisher port, ingestion job store port, replay audit store port, event publisher port, application command/result contracts, API DTO mapping, source-lineage contracts. | Historical/current-state deployable; revalidate before expanding. |
| `event_replay_service` | Replay, remediation, consumer DLQ recovery, bookkeeping repair, and operations control. | `app/application`, `app/dependencies.py`, `app/routers`; replay payload DTO anti-corruption remains transitional. | Replay command/query services. | Replay dispatch policy, replay audit contracts, ingestion operations DTO mapping, future replay/ops ports. | Historical/current-state deployable; revalidate before expanding. |
| `financial_reconciliation_service` | Financial controls, reconciliation finding policy, run execution, and evidence reads. | `app/domain`, `app/application`, `app/ports`, `app/adapters`, `app/routers`. | Reconciliation use cases. | Reconciliation repository ports, runtime-provider ports, finding mapper, reconciliation quality contracts. | Historical/current-state deployable; revalidate before expanding. |
| `persistence_service` | Event decoding, canonical persistence, idempotency, and completion publication. | Event adapters, persistence repositories, consumer boundaries, and shared event-mapping helpers. | Persistence event consumers and repository adapters. | Persistence event adapter records, `portfolio_common.event_mapping`, outbox payload contracts. | Historical/current-state deployable; revalidate before expanding. |
| `cost_calculator_service` | Cost basis, lot state, transaction fee/tax/linkage policy, and cost reprocessing. | Cost domain policies, consumer orchestration, repository adapters, and event mapping. | Cost calculation and reprocessing services. | Cost domain helpers, transaction replay ports, typed repository outputs, event contracts. | Historical/current-state deployable; revalidate before expanding. |
| `cashflow_calculator_service` | Cashflow classification, rule lookup, retry/DLQ handling, and outbox staging. | Cashflow rule policy, consumer orchestration, unit-of-work boundary, and repository adapters. | Cashflow processing workflow. | Cashflow processing outcome, unit-of-work boundary, DLQ/error contracts. | Historical/current-state deployable; revalidate before expanding. |
| `pipeline_orchestrator_service` | Stage-gate orchestration, readiness events, quiescence, and control-stage status. | Orchestration application services, stage repositories, event consumers, and event mapping. | Pipeline stage orchestration service. | Stage repository contracts, event-mapping adapters, quiescence support contracts. | Historical/current-state deployable; revalidate before expanding. |
| `position_calculator_service` | Position state, position history, original-backdated replay decisions, and outbox staging. | Pure position reducer, position orchestration service, repositories, and outbox adapters. | Position calculator orchestration. | `position_reducer`, repository ports/backlog, outbox event contracts, replay planning contracts. | Historical/current-state deployable; revalidate before expanding. |
| `valuation_orchestrator_service` | Valuation job orchestration, reprocessing state, and dispatch readiness. | Job scope helpers, scheduler/repository ports, and publisher adapters. | Valuation orchestration and scheduler services. | Valuation job publisher port, job scope contracts, scheduler recovery policies. | Historical/current-state deployable; revalidate before expanding. |
| `position_valuation_calculator` | Position valuation worker, valuation snapshot mutation, and active valuation handoff. | Worker consumer boundaries, valuation policies, repository adapters, and event mapping. | Valuation compute worker. | Valuation job event contracts, snapshot persistence contracts, metrics/readiness support. | Historical/current-state deployable; revalidate before expanding. |
| `timeseries_generator_service` | Position-timeseries generation and aggregation job staging. | Timeseries consumer boundaries, upsert helpers, stale-job reset, and aggregation staging. | Timeseries generation service. | Timeseries repository contracts, aggregation job staging contracts. | Historical/current-state deployable; revalidate before expanding. |
| `portfolio_aggregation_service` | Portfolio aggregation scheduling, aggregation job claim, portfolio-timeseries computation, and completion publication. | Scheduler ports, infrastructure adapters, dispatch planner, repository provider, metrics sink, and clock. | Aggregation scheduler/orchestrator. | Aggregation scheduler ports, aggregation job publisher port, completion event contract. | Historical/current-state deployable; revalidate before expanding. |
| `query_service` | Operational read plane for portfolio, position, transaction, market/reference, lookup, and reporting-oriented source reads. | API routers, application query services, source-data builders, repository-output typed records. | Query application services. | Source-data products, repository capability ports, response builders, API DTO mapping, OpenAPI metadata. | Historical/current-state deployable; revalidate before expanding. |
| `query_control_plane_service` | Analytics inputs, support/lineage, simulations, integration policy, capabilities, operations, and export lifecycle. | Control-plane routers, application services, support/evidence builders, policy modules, and dependencies. | Control-plane application services. | RFC-0082 contract-family inventory, source-data products, simulation/core snapshot commands, capability policies. | Historical/current-state deployable; revalidate before expanding. |

## Runtime Split Rationale Matrix

All entries below are current-state revalidation, not new runtime split approval.

| Deployable | Scale Driver | Deployment Cadence Driver | Operations Owner Driver | Persistence Owner Driver | Failure Isolation Driver | Security Boundary Driver |
| --- | --- | --- | --- | --- | --- | --- |
| `ingestion_service` | Bounded by write-ingress and upload load; scale evidence must come from ingestion throughput and parser budgets. | May change with source onboarding and write-contract validation. | Ingestion operations and replay support need clear support ownership. | Owns ingestion job and ingress payload state. | Isolates write-ingress failures from read APIs and calculators. | Write APIs need stricter auth, audit, and payload controls than read planes. |
| `event_replay_service` | Bounded by operator replay volume, not normal transaction throughput. | Changes with remediation workflows and DLQ support tools. | Operator/recovery ownership is distinct from normal ingestion. | Shares ingestion/replay audit state; persistence ownership must remain explicit. | Keeps replay/remediation failures away from normal write and read paths. | Protected operations endpoints require tighter authorization and audit. |
| `financial_reconciliation_service` | Runs control workloads that may spike after aggregation or replay. | Control logic may evolve independently of calculators. | Financial control ownership is distinct from calculator ownership. | Owns reconciliation run and finding records. | Reconciliation failures should not stop core persistence or calculation consumers. | Control evidence surfaces need operator-only access and audit. |
| `persistence_service` | Scales with raw domain event persistence volume. | Persistence schema and idempotency behavior can evolve apart from API routes. | Persistence/runtime ownership is event-store focused. | Owns canonical persistence writes. | Persistence lag/failures are isolated from calculators and API read surfaces. | Consumes trusted internal topics; security boundary is mainly event-ingress integrity. |
| `cost_calculator_service` | Scales with transaction and replay cost-calculation workload. | Cost policy changes may ship independently. | Cost engine ownership is separate from ingestion and read APIs. | Owns cost and lot-state writes. | Cost failures should not block raw persistence. | Internal calculator boundary; no public API exposure. |
| `cashflow_calculator_service` | Scales with transaction cashflow classification workload. | Cashflow policy changes may ship independently. | Cashflow processing owner is separate from cost and positions. | Owns cashflow writes and rule reads. | Cashflow failures should not block cost or raw persistence. | Internal calculator boundary; no public API exposure. |
| `pipeline_orchestrator_service` | Scales with stage-state fan-in and readiness events. | Orchestration rules can change independently of calculators. | Stage-gate operations owner is distinct from calculator owners. | Owns pipeline stage state. | Stage-gate failures should be visible without corrupting calculator state. | Internal orchestration boundary; no public API exposure. |
| `position_calculator_service` | Scales with transaction-to-position mutation volume and replay load. | Position policy changes may ship independently. | Position state owner is separate from cost/cashflow. | Owns position state and history writes. | Position replay/fencing failures should not block raw persistence. | Internal calculator boundary; no public API exposure. |
| `valuation_orchestrator_service` | Scales with valuation job scheduling, reprocessing, and market-data fan-out. | Job orchestration and reprocessing policy may ship independently. | Valuation orchestration owner is separate from compute worker. | Owns valuation job and reprocessing state. | Scheduler/orchestration failure should not corrupt valuation compute writes. | Internal orchestration boundary; no public API exposure. |
| `position_valuation_calculator` | Scales with valuation job compute volume. | Compute policy may ship independently of scheduler. | Valuation compute owner is distinct from orchestration. | Mutates valuation fields on position snapshots. | Compute failures should not stop scheduler state management. | Internal worker boundary; no public API exposure. |
| `timeseries_generator_service` | Scales with valuation snapshot to timeseries materialization volume. | Timeseries generation policy may ship independently. | Timeseries owner is distinct from valuation and aggregation. | Owns position-timeseries writes and aggregation job staging. | Timeseries failures should not corrupt valuation snapshots. | Internal worker boundary; no public API exposure. |
| `portfolio_aggregation_service` | Scales with portfolio-day aggregation volume and scheduler batches. | Aggregation policy and scheduler behavior may ship independently. | Aggregation owner is distinct from timeseries generator. | Owns portfolio-timeseries writes and aggregation job state. | Aggregation failure should not corrupt position-timeseries output. | Internal worker boundary; no public API exposure. |
| `query_service` | Scales with downstream read traffic and export-like source reads. | API read contracts may ship independently of write/calculator services. | Read-plane operations owner is distinct from write/worker owner. | Read-only over canonical/calculator tables; no source mutation. | Read failures should not block ingestion or calculators. | Public/read API authorization and audit differ from worker trust. |
| `query_control_plane_service` | Scales with support, analytics-input, simulation, and policy contract traffic. | Control-plane contracts may evolve independently of operational reads. | Support/policy/analytics-input ownership is distinct from basic reads. | Read-only plus control/export metadata. | Control-plane issues should not degrade basic operational reads. | Operator, policy, and analytics-input capabilities require stricter entitlement and audit. |

## No Split Yet Patterns

| In-Process Module Or Workflow | Current Home | No-Split-Yet Rationale | Reconsider Runtime Split Only When |
| --- | --- | --- | --- |
| Valuation scheduler loop | `position_valuation_calculator` and `valuation_orchestrator_service` orchestration paths | Current scheduler, claim, recovery, and dispatch logic is testable through ports and guards without another deployable. | Independent scheduler scaling, ownership, failure isolation, or SLO evidence shows the in-process scheduler is insufficient. |
| Simulation sessions and core snapshot identity | `query_control_plane_service` and `query_service` application/query services | Session-based simulation keeps operational complexity lower and reuses canonical read paths. | Async simulation workload, latency, or isolation evidence justifies a dedicated runtime. |
| Ingestion upload parser and validation policy | `ingestion_service` | Upload parsing, validation, preview, commit policy, and publishing are already separated by component and publisher-port boundaries. | Upload throughput, parser resource isolation, or security scanning requirements demand separate operation. |
| Replay payload dispatch and DTO anti-corruption | `event_replay_service` | Replay payload compatibility belongs beside replay commands while DTO-to-command migration proceeds. | Replay volume or security requirements require isolated replay execution beyond current protected endpoints. |
| Proof and support evidence builders | Service-local application/support packages | Evidence should be built from application/domain results inside the owning service before considering a proof service. | Proof artifact generation becomes independently scaled, independently owned, or externally published with a distinct support SLO. |

## Service Responsibility Map

| Service | Primary Role | Owns State | Consumes | Emits | Trigger Type |
| --- | --- | --- | --- | --- | --- |
| `ingestion_service` | Canonical write-ingress and contract validation | Canonical ingress submission state and request payload persistence | HTTP API | Raw domain topics (`transactions.raw.received`, `instruments.received`, `market_prices.raw.received`, `fx_rates.raw.received`, `business_dates.raw.received`, `portfolios.raw.received`) | API |
| `event_replay_service` | Replay/remediation control plane for ingestion jobs, DLQ recovery, and RFC-065 diagnostics | `ingestion_jobs`, `ingestion_job_failures`, `ingestion_ops_control`, `consumer_dlq_*` | HTTP API | Republished raw domain topics via controlled replay | API |
| `financial_reconciliation_service` | Independent financial controls plane for cross-domain reconciliation and integrity verification | `financial_reconciliation_runs`, `financial_reconciliation_findings` | HTTP API, `portfolio_day.reconciliation.requested` | `portfolio_day.reconciliation.completed` | API + Event |
| `persistence_service` | Canonical persistence and completion publication | `portfolios`, `transactions`, `instruments`, `market_prices`, `fx_rates`, `business_dates` | Raw domain topics | `transactions.persisted`, `market_prices.persisted` | Event |
| `cost_calculator_service` | Cost basis and lot-state authority | `transaction_costs`, `position_lot_state`, `accrued_income_offset_state`, `position_state` | `transactions.persisted`, `transactions.reprocessing.requested` | `transactions.cost.processed` | Event |
| `cashflow_calculator_service` | Cashflow rule/classification authority | `cashflows`, `cashflow_rules` | `transactions.persisted` | `cashflows.calculated` | Event |
| `pipeline_orchestrator_service` | Stage-gate orchestrator for deterministic downstream readiness | `pipeline_stage_state` | `transactions.cost.processed`, `cashflows.calculated`, `portfolio_day.aggregation.completed`, `portfolio_day.reconciliation.completed` | `transaction_processing.ready`, `portfolio_security_day.valuation.ready`, `portfolio_day.reconciliation.requested`, `portfolio_day.controls.evaluated` | Event |
| `position_calculator_service` | Position history and snapshot materialization | `position_history`, `daily_position_snapshots`, `position_state` | `transaction_processing.ready`, `transactions.cost.processed` (replay path) | `valuation.snapshot.persisted`, `transactions.reprocessing.requested` | Event |
| `valuation_orchestrator_service` | Valuation orchestration (job creation, scheduling, and reprocessing) | `portfolio_valuation_jobs`, `instrument_reprocessing_state`, `reprocessing_jobs` | `portfolio_security_day.valuation.ready`, `market_prices.persisted` | `valuation.job.requested` | Event + scheduler |
| `position_valuation_calculator` | Valuation compute worker and active valuation handoff publication | `daily_position_snapshots` (valuation fields) | `valuation.job.requested` | `valuation.snapshot.persisted` | Event |
| `timeseries_generator_service` | Position-timeseries compute worker and aggregation staging | `position_timeseries`, `portfolio_aggregation_jobs` | `valuation.snapshot.persisted` | no direct Kafka stage-completion topic in current runtime | Event |
| `portfolio_aggregation_service` | Portfolio aggregation orchestration and portfolio-timeseries compute | `portfolio_timeseries`, `portfolio_aggregation_jobs` | `portfolio_day.aggregation.job.requested` | `portfolio_day.aggregation.job.requested`, `portfolio_day.aggregation.completed` | Event + scheduler |
| `query_service` | Core read-plane APIs for canonical portfolio, position, transaction, market-data, and lookup reads | Read-only over canonical/calculator tables | HTTP API | N/A | API |
| `query_control_plane_service` | Control-plane APIs for integration contracts, operational diagnostics, and simulation workflows | Read-only over canonical/calculator tables plus export/control metadata | HTTP API | N/A | API |

## Stage Gate Sequence (Current)

1. `persistence_service` emits `transactions.persisted`.
2. `cost_calculator_service` emits `transactions.cost.processed`.
3. `cashflow_calculator_service` emits `cashflows.calculated`.
4. `pipeline_orchestrator_service` waits until both signals are observed for `(stage_name, transaction_id, epoch)` and emits `transaction_processing.ready`.
5. For security-scoped transactions, orchestrator also emits `portfolio_security_day.valuation.ready` to stage valuation jobs deterministically.
6. `valuation_orchestrator_service` creates and dispatches `valuation.job.requested` jobs; `position_valuation_calculator` consumes those jobs and persists valuation snapshots.
7. `timeseries_generator_service` consumes `valuation.snapshot.persisted` as the active valuation-to-timeseries trigger.
8. `timeseries_generator_service` stages aggregation jobs immediately after position-timeseries persistence.
9. `portfolio_aggregation_service` claims eligible aggregation jobs, emits `portfolio_day.aggregation.job.requested`, computes portfolio timeseries, and emits `portfolio_day.aggregation.completed`.
10. `pipeline_orchestrator_service` consumes `portfolio_day.aggregation.completed` and emits `portfolio_day.reconciliation.requested` for deterministic post-aggregation controls.
11. `financial_reconciliation_service` consumes `portfolio_day.reconciliation.requested`, runs the automatic reconciliation bundle with deterministic dedupe keys per `(reconciliation_type, portfolio_id, business_date, epoch)`, and emits `portfolio_day.reconciliation.completed`.
12. `pipeline_orchestrator_service` consumes `portfolio_day.reconciliation.completed`, upserts the `FINANCIAL_RECONCILIATION` portfolio-day control stage using monotonic status merge, and emits `portfolio_day.controls.evaluated`.
13. `portfolio_day.controls.evaluated` is the canonical portfolio-day controls decision:
    `controls_blocking=true` and `publish_allowed=false` for `FAILED` / `REQUIRES_REPLAY`,
    otherwise `controls_blocking=false` and `publish_allowed=true`.

## Stage Gate Sequence (Planned in RFC 081)

1. Route valuation/timeseries stage transitions through orchestrator-issued readiness events.
2. Keep all downstream calculators blind to source mode; calculators only react to canonical gate events.

## Reliability Rules

- All mutating services must enforce idempotency at consumer boundary (`processed_events`).
- Event publication must use outbox pattern (`outbox_events`) for exactly-once effect semantics.
- Stage transitions must be deterministic and epoch-aware; no implicit downstream trigger assumptions.
- Any replay path must preserve transaction epoch and stage-gate invariants.
- Control-plane replay/remediation services must preserve RFC-065 guardrails:
  durable audit trails, deterministic replay fingerprints, capacity/policy introspection,
  and protected operational endpoints.
- Control-plane reconciliation services must use the same RFC-065 operational standard:
  dedicated health/metrics surfaces, durable audit records, and deterministic rerunnable checks
  that never mutate calculator-owned tables.
- Automatic controls triggered by orchestrator events must remain idempotent across replay and duplicate delivery,
  using deterministic run-level dedupe keys rather than best-effort in-memory suppression.
- Control-stage status must be monotonic for a given `(portfolio_id, business_date, epoch, stage_name)` scope:
  duplicate or late events may preserve or worsen status (`COMPLETED -> REQUIRES_REPLAY -> FAILED`)
  but must never silently downgrade a blocking outcome back to `COMPLETED`.
- Support/control-plane APIs must surface the latest portfolio-day control decision so downstream
  operators and consumers cannot infer publishability from partial calculator progress alone.
