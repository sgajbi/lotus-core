# Lotus Core Microservice Boundaries and Trigger Matrix

Last updated: 2026-03-07  
Source authority: RFC 081

## Service Responsibility Map

| Service | Primary Role | Owns State | Consumes | Emits | Trigger Type |
| --- | --- | --- | --- | --- | --- |
| `ingestion_service` | Canonical write-ingress and contract validation | Canonical ingress submission state and request payload persistence | HTTP API | Raw domain topics (`raw_transactions`, `instruments`, `market_prices`, `fx_rates`) | API |
| `event_replay_service` | Replay/remediation control plane for ingestion jobs, DLQ recovery, and RFC-065 diagnostics | `ingestion_jobs`, `ingestion_job_failures`, `ingestion_ops_control`, `consumer_dlq_*` | HTTP API | Republished raw domain topics via controlled replay | API |
| `financial_reconciliation_service` | Independent financial controls plane for cross-domain reconciliation and integrity verification | `financial_reconciliation_runs`, `financial_reconciliation_findings` | HTTP API | N/A | API |
| `persistence_service` | Canonical persistence and completion publication | `portfolios`, `transactions`, `instruments`, `market_prices`, `fx_rates`, `business_dates` | Raw domain topics | `raw_transactions_completed`, `market_price_persisted` | Event |
| `cost_calculator_service` | Cost basis and lot-state authority | `transaction_costs`, `position_lot_state`, `accrued_income_offset_state`, `position_state` | `raw_transactions_completed`, `transactions_reprocessing_requested` | `processed_transactions_completed` | Event |
| `cashflow_calculator_service` | Cashflow rule/classification authority | `cashflows`, `cashflow_rules` | `raw_transactions_completed` | `cashflow_calculated` | Event |
| `pipeline_orchestrator_service` | Stage-gate orchestrator for deterministic downstream readiness | `pipeline_stage_state` | `processed_transactions_completed`, `cashflow_calculated` | `transaction_processing_completed`, `portfolio_day_ready_for_valuation` | Event |
| `position_calculator_service` | Position history and snapshot materialization | `position_history`, `daily_position_snapshots`, `position_state` | `transaction_processing_completed`, `processed_transactions_completed` (replay path) | `daily_position_snapshot_persisted`, `transactions_reprocessing_requested` | Event |
| `valuation_orchestrator_service` | Valuation orchestration (job creation, scheduling, and reprocessing) | `portfolio_valuation_jobs`, `instrument_reprocessing_state`, `reprocessing_jobs` | `portfolio_day_ready_for_valuation`, `market_price_persisted` | `valuation_required` | Event + scheduler |
| `position_valuation_calculator` | Valuation compute worker and completion publication | `daily_position_snapshots` (valuation fields) | `valuation_required` | `daily_position_snapshot_persisted`, `valuation_day_completed` | Event |
| `timeseries_generator_service` | Position-timeseries compute worker and completion publication | `position_timeseries`, `portfolio_aggregation_jobs` | `daily_position_snapshot_persisted`, `valuation_day_completed` | `position_timeseries_day_completed` | Event |
| `portfolio_aggregation_service` | Portfolio aggregation orchestration and portfolio-timeseries compute | `portfolio_timeseries`, `portfolio_aggregation_jobs` | `portfolio_aggregation_required` | `portfolio_aggregation_required`, `portfolio_aggregation_day_completed` | Event + scheduler |
| `query_service` | Core read-plane APIs for canonical portfolio, position, transaction, market-data, and lookup reads | Read-only over canonical/calculator tables | HTTP API | N/A | API |
| `query_control_plane_service` | Control-plane APIs for integration contracts, operational diagnostics, and simulation workflows | Read-only over canonical/calculator tables plus export/control metadata | HTTP API | N/A | API |

## Stage Gate Sequence (Current)

1. `persistence_service` emits `raw_transactions_completed`.
2. `cost_calculator_service` emits `processed_transactions_completed`.
3. `cashflow_calculator_service` emits `cashflow_calculated`.
4. `pipeline_orchestrator_service` waits until both signals are observed for `(stage_name, transaction_id, epoch)` and emits `transaction_processing_completed`.
5. For security-scoped transactions, orchestrator also emits `portfolio_day_ready_for_valuation` to stage valuation jobs deterministically.
6. `valuation_orchestrator_service` creates and dispatches `valuation_required` jobs; `position_valuation_calculator` consumes those jobs and emits `valuation_day_completed` after persisting valuation snapshots.
7. `timeseries_generator_service` consumes `valuation_day_completed` as the canonical valuation-to-timeseries trigger (while retaining `daily_position_snapshot_persisted` compatibility).
8. `timeseries_generator_service` emits `position_timeseries_day_completed` after position-timeseries persistence and stages aggregation jobs.
9. `portfolio_aggregation_service` claims eligible aggregation jobs, emits `portfolio_aggregation_required`, computes portfolio timeseries, and emits `portfolio_aggregation_day_completed`.

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
