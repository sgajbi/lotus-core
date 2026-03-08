# RFC-065 Calculator Scalability Operations Playbook

## Purpose
This runbook operationalizes RFC-065 for on-call and platform operators.
It defines measurable trigger signals, deterministic response actions, and
recovery guardrails for event-driven calculator scaling and replay safety.

## Scope
- Position calculator
- Cost calculator
- Valuation calculator
- Cashflow calculator
- Timeseries generator
- Ingestion operations control plane signals used to gate replay pressure

## Canonical Signals
- `rho`: utilization ratio (`lambda_in / (N_replica * mu_msg)`)
- `T_lag`: oldest unprocessed event age (seconds)
- `L_lag`: consumer lag size (events)
- `S_p95`: p95 end-to-end service time (seconds)
- `J_backlog`: non-terminal ingestion backlog (`accepted + queued`)
- `P_replay`: replay pressure (`replay_record_count / replay_max_records`)
- `P_dlq`: DLQ pressure (`dlq_events_in_window / dlq_budget_events_per_window`)

## Operating Bands
Use these bands consistently for all calculator groups.

| Band | Condition | Standard Action |
|---|---|---|
| Green | `rho < 0.60` and `T_lag < 15s` | Hold baseline replicas |
| Yellow | `0.60 <= rho < 0.80` or `15s <= T_lag < 60s` | Scale up one step, monitor DLQ pressure |
| Orange | `0.80 <= rho < 0.95` or `60s <= T_lag < 180s` | Aggressive autoscale, pause non-critical replay |
| Red | `rho >= 0.95` or `T_lag >= 180s` | Incident mode, block replay except emergency paths |

## Required Operational APIs
These endpoints are hosted by `event_replay_service` after the RFC 081 control-plane split.

- `GET /ingestion/health/summary`
- `GET /ingestion/health/consumer-lag`
- `GET /ingestion/health/slo`
- `GET /ingestion/health/error-budget`
- `GET /ingestion/health/backlog-breakdown`
- `GET /ingestion/health/stalled-jobs`
- `GET /ingestion/dlq/consumer-events`
- `GET /ingestion/audit/replays`
- `PUT /ingestion/ops/control`

## Incident Workflow
1. Confirm severity with `GET /ingestion/health/slo` and `GET /ingestion/health/error-budget`.
2. Isolate pressure source:
- Backlog hotspot: `GET /ingestion/health/backlog-breakdown`
- Stalled jobs: `GET /ingestion/health/stalled-jobs`
- Consumer failure concentration: `GET /ingestion/dlq/consumer-events`
3. Apply control-plane mode:
- `normal`: default
- `drain`: stop new ingestion writes, continue queue drain
- `paused`: stop ingestion writes and replay requests
4. Guard replay blast radius:
- allow replay only if backlog and replay pressure guardrails are within limits
- prefer dry-run path for uncertain payload mappings
5. Return to steady state:
- reduce lag/age below yellow threshold
- replay only deterministic, auditable batches
- switch mode back to `normal`

## Replay Safety Rules
- Never run broad replay while in orange/red band.
- Do not exceed configured replay maximum records per request.
- Do not replay when ingestion backlog exceeds replay threshold.
- Every replay must produce audit evidence (`consumer_dlq_replay_audit`).

## Scaling Controls
- Deploy KEDA scaled objects from:
  - `deployment/kubernetes/keda/calculator-scaledobjects.yaml`
- Validate scaling objects:
  - `kubectl get scaledobject -n lotus-core`
  - `kubectl describe scaledobject <name> -n lotus-core`

## CI Gate Expectations
Minimum required CI evidence for RFC-065 operational correctness:
- `Tests (ops-contract)` validates ingestion ops contract and expected response shape.
- `Tests (integration-lite)` validates query-service integration basics.
- `Latency Gate` and `Docker Smoke Contract` remain required.

## Exit Criteria for Incident
- No red-band signal for 30 minutes.
- DLQ pressure below 1.0 for two consecutive lookback windows.
- Backlog trend non-increasing and oldest backlog age below critical threshold.
- Replay queue empty or bounded with audited completion plan.
