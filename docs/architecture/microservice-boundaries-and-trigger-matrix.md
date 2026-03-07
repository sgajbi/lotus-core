# Lotus Core Microservice Boundaries and Trigger Matrix

Last updated: 2026-03-07  
Source authority: RFC 081

## Service Responsibility Map

| Service | Primary Role | Owns State | Consumes | Emits | Trigger Type |
| --- | --- | --- | --- | --- | --- |
| `ingestion_service` | Canonical write-ingress and contract validation | `ingestion_jobs`, `ingestion_job_failures`, `ingestion_ops_control`, `consumer_dlq_*` | HTTP API | Raw domain topics (`raw_transactions`, `instruments`, `market_prices`, `fx_rates`) | API |
| `persistence_service` | Canonical persistence and completion publication | `portfolios`, `transactions`, `instruments`, `market_prices`, `fx_rates`, `business_dates` | Raw domain topics | `raw_transactions_completed`, `market_price_persisted` | Event |
| `cost_calculator_service` | Cost basis and lot-state authority | `transaction_costs`, `position_lot_state`, `accrued_income_offset_state`, `position_state` | `raw_transactions_completed`, `transactions_reprocessing_requested` | `processed_transactions_completed` | Event |
| `cashflow_calculator_service` | Cashflow rule/classification authority | `cashflows`, `cashflow_rules` | `raw_transactions_completed` | `cashflow_calculated` | Event |
| `pipeline_orchestrator_service` | Stage-gate orchestrator for deterministic downstream readiness | `pipeline_stage_state` | `processed_transactions_completed`, `cashflow_calculated` | `transaction_processing_completed` | Event |
| `position_calculator_service` | Position history and snapshot materialization | `position_history`, `daily_position_snapshots`, `position_state` | `processed_transactions_completed` | `daily_position_snapshot_persisted`, `transactions_reprocessing_requested` | Event |
| `position_valuation_calculator` | Valuation scheduling and valuation computation | `portfolio_valuation_jobs`, `instrument_reprocessing_state`, `reprocessing_jobs` | `daily_position_snapshot_persisted`, `market_price_persisted`, `valuation_required` | `position_valued`, `valuation_required` | Event + scheduler |
| `timeseries_generator_service` | Position and portfolio timeseries generation | `position_timeseries`, `portfolio_timeseries`, `portfolio_aggregation_jobs` | `position_valued`, `portfolio_aggregation_required` | `position_timeseries_generated`, `portfolio_timeseries_generated`, `portfolio_aggregation_required` | Event + scheduler |
| `query_service` | Read-plane APIs and operational diagnostics | Read-only over canonical/calculator tables | HTTP API | N/A | API |

## Stage Gate Sequence (Current)

1. `persistence_service` emits `raw_transactions_completed`.
2. `cost_calculator_service` emits `processed_transactions_completed`.
3. `cashflow_calculator_service` emits `cashflow_calculated`.
4. `pipeline_orchestrator_service` waits until both signals are observed for `(stage_name, transaction_id, epoch)` and emits `transaction_processing_completed`.

## Stage Gate Sequence (Planned in RFC 081)

1. Extend orchestrator to emit `portfolio_day_ready_for_valuation`.
2. Route valuation/timeseries stage transitions through orchestrator-issued readiness events.
3. Keep all downstream calculators blind to source mode; calculators only react to canonical gate events.

## Reliability Rules

- All mutating services must enforce idempotency at consumer boundary (`processed_events`).
- Event publication must use outbox pattern (`outbox_events`) for exactly-once effect semantics.
- Stage transitions must be deterministic and epoch-aware; no implicit downstream trigger assumptions.
- Any replay path must preserve transaction epoch and stage-gate invariants.
