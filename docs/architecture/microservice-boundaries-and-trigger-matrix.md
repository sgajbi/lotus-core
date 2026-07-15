# Lotus Core Microservice Boundaries and Trigger Matrix

Last updated: 2026-07-15
Source authority: RFC 081

Runtime-boundary governance: this matrix documents current-state service responsibilities. It is
not approval evidence for new deployable splits. New or expanded deployable boundaries must follow
`docs/standards/runtime-boundary-decision-standard.md` and be cataloged in
`docs/architecture/runtime-boundary-decision-catalog.json`.

Related boundary records:

1. Current-state architecture map: `docs/architecture/current-state-architecture-map.md`
2. Target architecture: `docs/architecture/lotus-core-target-architecture.md`
3. Runtime-boundary decision standard: `docs/standards/runtime-boundary-decision-standard.md`
4. Runtime-boundary decision catalog: `docs/architecture/runtime-boundary-decision-catalog.json`
5. In-process modularity standard: `docs/standards/in-process-modularity-package-standard.md`
6. In-process boundary contract: `docs/standards/in-process-boundary-contract-standard.md`
7. Calculator consolidation decision: `docs/architecture/calculator-runtime-consolidation-decision.md`

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
| `financial_reconciliation_service` | Financial controls, reconciliation finding policy, run execution, control evidence, and completion publication. | `app/domain`, `app/application`, `app/ports`, `app/infrastructure`, `app/adapters`, `app/routers`. | Reconciliation and control-evidence use cases. | Reconciliation repository ports, control-evidence/event-staging ports, finding mapper, reconciliation quality contracts. | Active controls deployable; owns the former reconciliation-to-controls transition. |
| `persistence_service` | Event decoding, canonical persistence, idempotency, and completion publication. | Event adapters, persistence repositories, consumer boundaries, and shared event-mapping helpers. | Persistence event consumers and repository adapters. | Persistence event adapter records, `portfolio_common.event_mapping`, outbox payload contracts. | Historical/current-state deployable; revalidate before expanding. |
| `portfolio_transaction_processing_service` | Atomic booked-transaction cost, cashflow, position, transaction readiness, idempotency, compatibility outbox, and replay-request processing. | Delivery mappers, `ProcessTransactionUseCase`, separate financial modules/policies, readiness use case, ports, SQLAlchemy adapters, one unit of work, two consumers, aggregate health/metrics. | Transaction processing runtime. | Typed commands/results, financial module ports, readiness/replay ports, observer port, compatibility event contracts. | Active app-local/CI deployable; registry/Kubernetes cutover pending. |
| `valuation_orchestrator_service` | Valuation job orchestration, reprocessing state, and dispatch readiness. | Job scope helpers, scheduler/repository ports, and publisher adapters. | Valuation orchestration and scheduler services. | Valuation job publisher port, job scope contracts, scheduler recovery policies. | Historical/current-state deployable; revalidate before expanding. |
| `position_valuation_calculator` | Position valuation worker, valuation snapshot mutation, and active valuation handoff. | Worker consumer boundaries, valuation policies, repository adapters, and event mapping. | Valuation compute worker. | Valuation job event contracts, snapshot persistence contracts, metrics/readiness support. | Historical/current-state deployable; revalidate before expanding. |
| `timeseries_generator_service` | Position-timeseries generation and aggregation job staging. | Timeseries consumer boundaries, upsert helpers, stale-job reset, and aggregation staging. | Timeseries generation service. | Timeseries repository contracts, aggregation job staging contracts. | Historical/current-state deployable; revalidate before expanding. |
| `portfolio_aggregation_service` | Portfolio aggregation scheduling, aggregation job claim, portfolio-timeseries computation, and completion publication. | Scheduler ports, infrastructure adapters, dispatch planner, repository provider, metrics sink, and clock. | Aggregation scheduler/orchestrator. | Aggregation scheduler ports, aggregation job publisher port, completion event contract. | Historical/current-state deployable; revalidate before expanding. |
| `query_service` | Operational read plane for portfolio, position, transaction, market/reference, lookup, and reporting-oriented source reads. | API routers, application query services, source-data builders, repository-output typed records. | Query application services. | Source-data products, repository capability ports, response builders, API DTO mapping, OpenAPI metadata. | Historical/current-state deployable; revalidate before expanding. |
| `query_control_plane_service` | Analytics inputs, support/lineage, simulations, integration policy, capabilities, operations, and export lifecycle. | Control-plane routers, application services, support/evidence builders, policy modules, and dependencies. | Control-plane application services. | RFC-0082 contract-family inventory, source-data products, simulation/core snapshot commands, capability policies. | Historical/current-state deployable; revalidate before expanding. |

## Runtime Split Rationale Matrix

This table records current evidence. Cost, cashflow, and position are separately owned modules in
one app-local/CI transaction-processing deployable. Physical legacy packages are removed locally;
registry/Kubernetes rollout still requires explicit release evidence.

| Deployable | Scale Driver | Deployment Cadence Driver | Operations Owner Driver | Persistence Owner Driver | Failure Isolation Driver | Security Boundary Driver |
| --- | --- | --- | --- | --- | --- | --- |
| `ingestion_service` | Bounded by write-ingress and upload load; scale evidence must come from ingestion throughput and parser budgets. | May change with source onboarding and write-contract validation. | Ingestion operations and replay support need clear support ownership. | Owns ingestion job and ingress payload state. | Isolates write-ingress failures from read APIs and calculators. | Write APIs need stricter auth, audit, and payload controls than read planes. |
| `event_replay_service` | Bounded by operator replay volume, not normal transaction throughput. | Changes with remediation workflows and DLQ support tools. | Operator/recovery ownership is distinct from normal ingestion. | Shares ingestion/replay audit state; persistence ownership must remain explicit. | Keeps replay/remediation failures away from normal write and read paths. | Protected operations endpoints require tighter authorization and audit. |
| `financial_reconciliation_service` | Runs control workloads that may spike after aggregation or replay. | Control logic may evolve independently of calculators. | Financial control ownership is distinct from calculator ownership. | Owns reconciliation runs/findings and authoritative portfolio-day control outcomes; persists compatibility rows for QCP support reads. | Reconciliation failures should not stop core persistence or calculation consumers. | Control evidence surfaces need operator-only access and audit. |
| `persistence_service` | Scales with raw domain event persistence volume. | Persistence schema and idempotency behavior can evolve apart from API routes. | Persistence/runtime ownership is event-store focused. | Owns canonical persistence writes. | Persistence lag/failures are isolated from calculators and API read surfaces. | Consumes trusted internal topics; security boundary is mainly event-ingress integrity. |
| `portfolio_transaction_processing_service` | One ordered booked-transaction stream plus independently tunable replay group; scale is bounded by Kafka partitions and DB capacity. | Cost, cashflow, and position policies ship as independently tested modules in one image. | One transaction-processing owner and one dashboard/runbook. | Financial tables remain module-owned behind one SQLAlchemy unit of work. | Any module failure rolls back cost, cashflow, position, idempotency, and outbox effects together. | One internal worker trust boundary; no business HTTP routes. |
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

## Transaction Calculator Consolidation Target

Cost, cashflow, and position processing run in one app-local/CI
`portfolio_transaction_processing_service` deployable. They remain separate domain/application
modules coordinated by one `ProcessTransactionUseCase` and one normal-path unit of work. Module
diagnostics, replay policy, DLQ reasons, metrics, and state ownership remain explicit. Release and
Kubernetes manifests are implemented locally and must never run target and legacy topologies together.

`position_valuation_calculator` remains independently deployable because its job-driven compute,
market-data dependency, scaling, backfill, and failure-isolation profile differs materially from
transaction processing.

## Enforced Stage Ownership Contracts

| Stage | Owner | Input contract | Output contract | Idempotency and replay | Produced state/read model |
| --- | --- | --- | --- | --- | --- |
| Cost processing | target cost module | mapped booked transaction inside `ProcessTransactionUseCase` | `transactions.cost.processed` compatibility event | Combined consumer claim plus cost checkpoint/replay policy; preserve transaction epoch and correlation. | Transaction cost, lot state, accrued offsets. |
| Cashflow processing | target cashflow module | cost-enriched staged transaction inside the same use case | `cashflows.calculated` compatibility event | Combined transport claim plus cashflow semantic fence; rule-backed rerun remains deterministic. | Cashflow rows and rule evidence. |
| Transaction readiness | target readiness module inside `ProcessTransactionUseCase` | completed cost, position, and cashflow effects in the same database transaction | `transaction_processing.ready`, `portfolio_security_day.valuation.ready`; `transactions.cost.processed` remains compatibility-only | Exact transaction-stage lock, monotonic epoch fence, one completion claim, and transactional outbox staging. | Transaction readiness evidence staged atomically with financial effects. |
| Position processing | target position module | cost/cashflow-complete transaction inside the same use case | durable position state; compatibility stage events remain external | Ordered reducer, combined claim, epoch fence, and inline backdated replay lock. | Position history, daily snapshots, position state. |
| Valuation orchestration | `valuation_orchestrator_service` | valuation readiness and market-price facts | `valuation.job.requested` | Job identity, claim lease, epoch, dispatch recovery, and bounded backfill. | Valuation jobs and reprocessing state. |
| Valuation compute | `position_valuation_calculator` | `valuation.job.requested` | `valuation.snapshot.persisted` | Job-event claim, snapshot mutation transaction, and outbox handoff. | Valued daily position snapshots. |
| Timeseries and aggregation | `timeseries_generator_service`, `portfolio_aggregation_service` | valuation snapshots and aggregation jobs | `portfolio_day.aggregation.completed` | Upsert/job claim, epoch, stale reset, and completion outbox. | Position and portfolio timeseries. |
| Financial controls | `portfolio_aggregation_service`, `financial_reconciliation_service` | aggregation completion | reconciliation request, completion compatibility fact, and `portfolio_day.controls.evaluated` | Deterministic run key, monotonic control status, latest-epoch suppression, and one DB/outbox transaction. | Reconciliation findings and publishability evidence. |

Architecture CI blocks both retired calculator paths and the unified transaction-processing package
from orchestrator/query internals. It also blocks orchestrators from calculator, unified transaction,
and query internals. Event CI requires every producer and consumer actor to resolve to the
runtime-boundary catalog.

## Service Responsibility Map

| Service | Primary Role | Owns State | Consumes | Emits | Trigger Type |
| --- | --- | --- | --- | --- | --- |
| `ingestion_service` | Canonical write-ingress and contract validation | Canonical ingress submission state and request payload persistence | HTTP API | Raw domain topics (`transactions.raw.received`, `instruments.received`, `market_prices.raw.received`, `fx_rates.raw.received`, `business_dates.raw.received`, `portfolios.raw.received`) | API |
| `event_replay_service` | Replay/remediation control plane for ingestion jobs, DLQ recovery, and RFC-065 diagnostics | `ingestion_jobs`, `ingestion_job_failures`, `ingestion_ops_control`, `consumer_dlq_*` | HTTP API | Republished raw domain topics via controlled replay | API |
| `financial_reconciliation_service` | Independent financial controls plane for cross-domain reconciliation, integrity verification, and publishability evidence | `financial_reconciliation_runs`, `financial_reconciliation_findings`, `FINANCIAL_RECONCILIATION` compatibility rows in `pipeline_stage_state` | HTTP API, `portfolio_day.reconciliation.requested` | `portfolio_day.reconciliation.completed`, `portfolio_day.controls.evaluated` | API + Event |
| `persistence_service` | Canonical persistence and completion publication | `portfolios`, `transactions`, `instruments`, `market_prices`, `fx_rates`, `business_dates` | Raw domain topics | `transactions.persisted`, `market_prices.persisted` | Event |
| `portfolio_transaction_processing_service` | Atomic transaction cost, cashflow, position, and readiness runtime with separate module authority | `transaction_costs`, `position_lot_state`, `average_cost_pool_state`, `cashflows`, `position_history`, `daily_position_snapshots`, `position_state`, transaction readiness state, idempotency/outbox | `transactions.persisted`, `transactions.reprocessing.requested` | `transaction_processing.ready`, `portfolio_security_day.valuation.ready`, plus `transactions.cost.processed` and `cashflows.calculated` compatibility facts | Event |
| `valuation_orchestrator_service` | Valuation orchestration (job creation, scheduling, and reprocessing) | `portfolio_valuation_jobs`, `instrument_reprocessing_state`, `reprocessing_jobs` | `portfolio_security_day.valuation.ready`, `market_prices.persisted` | `valuation.job.requested` | Event + scheduler |
| `position_valuation_calculator` | Valuation compute worker and active valuation handoff publication | `daily_position_snapshots` (valuation fields) | `valuation.job.requested` | `valuation.snapshot.persisted` | Event |
| `timeseries_generator_service` | Position-timeseries compute worker and aggregation staging | `position_timeseries`, `portfolio_aggregation_jobs` | `valuation.snapshot.persisted` | no direct Kafka stage-completion topic in current runtime | Event |
| `portfolio_aggregation_service` | Lease-aware portfolio aggregation scheduling and portfolio-timeseries compute | `portfolio_timeseries`, `portfolio_aggregation_jobs` | durable `portfolio_aggregation_jobs` | `portfolio_day.aggregation.completed`, `portfolio_day.reconciliation.requested` | Durable queue + bounded workers |
| `query_service` | Core read-plane APIs for canonical portfolio, position, transaction, market-data, and lookup reads | Read-only over canonical/calculator tables | HTTP API | N/A | API |
| `query_control_plane_service` | Control-plane APIs for integration contracts, operational diagnostics, and simulation workflows | Read-only over canonical/calculator tables plus export/control metadata | HTTP API | N/A | API |

## Stage Gate Sequence (Current)

1. `persistence_service` emits `transactions.persisted`.
2. `portfolio_transaction_processing_service` commits cost, cashflow, position, idempotency, and
   compatibility outbox effects atomically.
3. The target readiness use case claims the current transaction epoch and stages
   `transaction_processing.ready` plus `portfolio_security_day.valuation.ready` in the same unit of
   work after cost, position, and cashflow effects succeed.
4. The target also emits `transactions.cost.processed` and `cashflows.calculated` as compatibility
   facts with no active in-repo consumers.
5. The valuation-ready event stages valuation jobs deterministically.
6. `valuation_orchestrator_service` creates and dispatches `valuation.job.requested` jobs; `position_valuation_calculator` consumes those jobs and persists valuation snapshots.
7. `timeseries_generator_service` consumes `valuation.snapshot.persisted` as the active valuation-to-timeseries trigger.
8. `timeseries_generator_service` stages aggregation jobs immediately after position-timeseries persistence.
9. `portfolio_aggregation_service` recovers expired leases, claims eligible aggregation jobs with
   fenced ownership, computes portfolio timeseries through bounded workers, and atomically stages
   both the `portfolio_day.aggregation.completed` compatibility fact and
   `portfolio_day.reconciliation.requested`.
10. `financial_reconciliation_service` consumes `portfolio_day.reconciliation.requested`, runs the automatic reconciliation bundle with deterministic dedupe keys per `(reconciliation_type, portfolio_id, business_date, epoch)`, persists monotonic/latest-epoch control evidence, and atomically stages `portfolio_day.reconciliation.completed` plus `portfolio_day.controls.evaluated` for the latest epoch.
11. `portfolio_day.controls.evaluated` is the canonical portfolio-day controls decision:
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
