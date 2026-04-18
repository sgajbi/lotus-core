# Lotus Core Microservice Boundaries and Trigger Matrix

Last updated: 2026-03-08  
Source authority: RFC 081

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
