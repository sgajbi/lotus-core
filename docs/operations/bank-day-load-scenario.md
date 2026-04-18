# Bank-Day Load Scenario

This runbook defines the governed `lotus-core` load scenario for a realistic
average banking day:

1. `1,000` portfolios,
2. `100` BUY transactions per portfolio,
3. `100,000` transactions total,
4. deterministic instrument, FX, and market-price support data,
5. end-to-end proof across ingestion, asynchronous processing, query APIs,
   reconciliation, health, and logs.

## Purpose

Use this scenario to answer customer-grade questions:

1. how long does `lotus-core` take to ingest and process a normal day,
2. when do query and support APIs become accurate and ready,
3. whether positions, valuations, and timeseries reconcile exactly,
4. whether worker health, backlog, and logs remain operationally clean.

## Automation

Run:

```powershell
python scripts\bank_day_load_scenario.py `
  --portfolio-count 1000 `
  --transactions-per-portfolio 100 `
  --transaction-batch-size 2000 `
  --sample-size 5 `
  --drain-timeout-seconds 7200
```

Artifacts are written to:

1. `output/task-runs/<run_id>-bank-day-load.json`
2. `output/task-runs/<run_id>-bank-day-load.md`

## Scenario Design

The script:

1. waits for ingestion, query, control-plane, event-replay, and reconciliation
   services to become ready,
2. seeds business date, portfolios, instruments, FX rates, and market prices
   through public ingestion APIs,
3. waits for supporting data to become durable in PostgreSQL before it submits
   transactions,
4. ingests deterministic BUY transactions in batches,
5. monitors event-replay health during processing,
6. waits for position snapshots, security-level position timeseries, and
   portfolio-level timeseries to converge,
7. samples downstream APIs,
8. runs reconciliation checks for sampled portfolios,
9. inspects container logs for real error lines,
10. writes a machine-readable and human-readable evidence pack.

## Deterministic Dataset Rules

1. Portfolios are USD base portfolios.
2. Instruments cycle through `USD`, `EUR`, `SGD`, and `GBP`.
3. Trade price rule: `50.00 + (index * 1.25)`.
4. Market price rule: `trade_price * 1.01`.
5. Quantity rule: one unit per BUY.
6. FX rate rule uses deterministic `USD_PER_CURRENCY` anchors:
   `USD=1.0`, `EUR=1.1`, `SGD=0.74`, `GBP=1.27`.

Because the dataset is deterministic, the harness can prove:

1. exact total transaction count,
2. exact total quantity,
3. exact per-security quantity,
4. exact total market value,
5. exact per-sampled-portfolio market value.

## Evidence Captured

The report records:

1. ingestion duration by endpoint,
2. drain duration until the asynchronous pipeline quiesces,
3. peak backlog jobs, backlog age, replay pressure, and DLQ count,
4. database tie-outs for portfolios, instruments, transactions, snapshots,
   position-timeseries, and portfolio-timeseries,
5. explicit stage-gap counts showing:
   - portfolios with snapshots but no position-timeseries yet,
   - portfolios with position-timeseries but no portfolio-timeseries yet,
6. split pending versus processing queue counts for valuation and aggregation,
7. latest materialization and job-update heartbeat timestamps for snapshots,
   position-timeseries, portfolio-timeseries, valuation jobs, and aggregation jobs,
8. count and oldest completion timestamp for valuation jobs that are already `COMPLETE` but
   still have no matching position-timeseries row,
9. valuation-to-position-timeseries handoff latency summary from durable facts,
10. sampled positions, transaction-window, and support-overview API latencies,
11. sampled reconciliation results,
12. log evidence for core processing services.

## Live Institutional Run Notes

The active institutional run `20260418T065154Z` on `2026-04-18` established three important
operator rules for this harness:

1. the harness process lifetime is not the same thing as pipeline completion; asynchronous
   services can keep materializing target-date artifacts after the original Python process exits,
2. when branch-only support telemetry has not yet been rolled into the running stack, use direct
   PostgreSQL facts as the source of truth and record the stale runtime route separately; after
   the targeted `2026-04-18` refresh for run `20260418T065154Z`, the support route returned the
   same completion facts directly,
3. completion diagnosis must separate snapshot coverage, security-level
   `position_timeseries` coverage, and portfolio-level `portfolio_timeseries` coverage because the
   main lag can sit between valuation completion and position-timeseries breadth rather than in
   portfolio aggregation.

For completed runs that already converged, use
`python scripts/bank_day_load_reconciliation_report.py --run-id <run_id> --business-date <YYYY-MM-DD>`
to collect sampled or exhaustive reconciliation evidence without reseeding data. Increase
`--portfolio-limit` to widen the proof set; the `20260418T065154Z` institutional run was
reconciled across all `1000` portfolios with this workflow.

## Current Known Harness Hardening

The harness now includes two protections discovered during smoke execution:

1. reference/master data materialization barriers before transaction load, so
   valuation does not race ahead of newly seeded instruments or prices,
2. run-unique synthetic ISIN generation, so repeated executions do not collide
   on instrument uniqueness constraints.

## Local Runtime Caveat

The local Docker stack is single-node and does not autoscale replicas. In local
proof, "scale up" and "scale down" should be interpreted as:

1. backlog growth under load,
2. queue drain and service recovery after load,
3. API readiness after processing completes.

For replica autoscaling proof, run the same harness in the target orchestrated
environment and capture:

1. replica counts over time,
2. CPU and memory utilization,
3. queue depth,
4. pod restart count,
5. service saturation signals.

## Smoke Evidence

A successful smoke execution already exists at:

1. `output/task-runs/20260418T050259Z-bank-day-load.json`
2. `output/task-runs/20260418T050259Z-bank-day-load.md`

That smoke run proved:

1. exact DB tie-out for counts and market value,
2. sampled API correctness for positions and transactions,
3. successful timeseries-integrity reconciliation on sampled portfolios,
4. zero real error lines across inspected services.
