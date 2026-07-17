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
python scripts\operations\bank_day_load_scenario.py `
  --compose-project-name lotus-core-app-local `
  --portfolio-count 1000 `
  --transactions-per-portfolio 100 `
  --transaction-batch-size 2000 `
  --sample-size 5 `
  --seed-materialization-timeout-seconds 600 `
  --resource-poll-interval-seconds 5 `
  --transaction-processing-base-url http://localhost:8090 `
  --drain-timeout-seconds 7200
```

Artifacts are written to:

1. `output/task-runs/<run_id>-bank-day-load.json`
2. `output/task-runs/<run_id>-bank-day-load.md`

For isolated dynamic-port execution, use the managed profile targets:

```powershell
make profile-derived-state-daily
make profile-derived-state-fan-in
make profile-derived-state-price-burst
make profile-derived-state-price-restatement
make profile-derived-state-fx-restatement
make test-derived-state-workload-smoke
```

`daily` is the certifying 1,000-portfolio x 100-position profile. `fan-in` is the certifying
one-portfolio x 1,000-position aggregation profile. `price-burst` first materializes 100 portfolios
x 100 shared instruments, then applies a 5% same-date price correction and requires all 10,000
snapshots and position rows plus 100 portfolio rows to carry post-correction timestamps and exact
corrected values. The smoke target is always recorded as
`evidence_classification=diagnostic`; it validates orchestration but cannot certify capacity or
close a #714 workload requirement. Certifying profiles fail fast unless `--build` is active, and
the repo-native profile targets supply it, so existing/stale local images cannot emit certifying
evidence.

Service readiness and seed materialization use separate deadlines. Readiness remains a short
startup check, while certifying profiles allow up to 600 seconds for source records to become
durable before transaction submission. Seed timeout failures remain hard failures and do not
weaken the downstream drain or reconciliation deadlines.

Current-business-date FX and market-price seed facts do not create replay merely because positions
have not been submitted yet. Later transaction processing emits authoritative valuation readiness
and reads those committed source facts. A delayed source notification also skips positions whose
same-day snapshots were materialized after that source row; a later correction updates the source
freshness and reopens valuation. Backdated and future source facts still require durable replay. A
daily run that creates materially more valuation-snapshot events than source position keys must be
investigated as work amplification rather than accepted by extending the drain deadline.
Likewise, a normal valuation job should have one claim and one completion transition in its
attempt count. Jobs with repeated normal-lifecycle transitions indicate duplicate scheduling or
rearm amplification. Different correlation ids are lineage evidence only and must not reopen
completed work; only a freshness-proven source correction can request explicit rearm.

`price-restatement` applies the same price correction across five business dates.
`fx-restatement` materializes the same 100 x 100 shape across five business dates, corrects the
direct `EUR/USD` rate by 5%, and requires exact affected snapshot, valuation-job,
position-timeseries, portfolio-timeseries, market-value, and unrealized price/FX/total P&L
evidence. It also requires one processed source observation, one completed pair replay, closed
valuation/aggregation/reprocessing/outbox queues, clean reconciliation, and complete resource
samples. Price and FX corrections intentionally remain separate profiles so one cannot mask the
other's scope or timing.

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
9. inspects stable Compose service logs for real error lines using the configured project/file,
10. writes a machine-readable and human-readable evidence pack.

When `--market-price-correction-multiplier` is supplied, the scenario runs the complete baseline
cycle first, records a database-clock correction boundary, ingests corrected prices, and waits for
every affected valuation job, snapshot, position series, and portfolio series row after that
boundary. The report records the correction phase and its drain duration separately.

When the complete `--fx-rate-correction-from-currency`,
`--fx-rate-correction-to-currency`, and `--fx-rate-correction-multiplier` set is supplied, the
scenario accepts only a direct pair into the USD portfolio base, rejects an irrelevant pair with no
affected instruments, ingests the correction through the public FX endpoint, and independently
calculates the corrected market value and P&L decomposition. The database evidence then proves the
source observation and pair replay were each processed exactly once. Do not combine price and FX
corrections in one run.

The certifying FX profile also stops `valuation_orchestrator_service` before correction ingestion,
restores it with Compose health waiting, and only then starts the exact evidence drain. This proves
that a committed persisted observation survives consumer interruption. Runtime restoration is
unconditional, including when correction ingestion fails. The report records measured stop and
healthy-restore UTC timestamps, outage duration, service identity, and Compose health-wait outcome;
the profile fails when restart was requested but measured recovery evidence is absent.

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
9. valuation-to-position and position-to-portfolio materialization latency summaries from durable
   facts, including p50, p95, p99, maximum, and sample count for each stage,
10. peak PostgreSQL connection utilization, active and idle-in-transaction connections, lock
    waiters, and blocked sessions sampled during the workload,
11. peak CPU and memory utilization for the exact `portfolio_derived_state_service` Compose
    container,
12. sampled positions, transaction-window, and support-overview API latencies,
13. sampled reconciliation results,
14. log evidence for core processing services.

An FX-restatement report also records normalized pair identity, effective date, initial and
corrected rates, expected and observed affected row counts, exact corrected market values,
unrealized price/FX/total components, processed-observation count, pair-replay count, and every
relevant final queue/failure count. Missing evidence fails the report; a successful ingestion
response is not correction proof.

The report config records `evidence_classification` as `certifying` or `diagnostic`, together with
`source_revision` and `source_tree_state`. The revision is the exact Git commit when repository
metadata is available; the tree state is `clean`, `dirty`, or `unavailable` and never retains file
names or command output. Do not infer certification from a successful exit code, scenario name, or
source-revision field: local evidence remains lower-class than trusted CI or receipt-bound runtime
evidence.

The report records the database backend, host, port, and database name under `database_target`.
It never records the connection URL, username, password, or URL query parameters. Treat generated
JSON, Markdown, diagnostics, and logs as security-sensitive evidence even when `output/` is ignored
by Git; run `make synthetic-fixture-leakage-guard` before retaining or sharing an evidence pack.

The valuation-to-position sample is one completed valuation job joined to its matching
position-timeseries row. The position-to-portfolio sample is one portfolio, business date, and epoch;
its clock starts when the last matching position row was updated and stops when the portfolio row was
updated. Both stages use upsert-aware `updated_at` timestamps and clamp negative database-clock
differences to zero. The scenario fails when the first-stage sample count differs from the generated
position count or the second-stage sample count differs from the generated portfolio count.
The scenario also fails when it cannot complete at least one time-aligned database-and-container
resource sample. Sampling diagnostics retain bounded exception types only; they do not persist
command output or connection details.

Before the managed stack is torn down, the scenario also scrapes the combined transaction-runtime
metrics endpoint once and records one bounded entry per `stage` and `outcome`. Each entry contains
the operation counter, duration observation count, cumulative duration, and mean duration. This
allows cost, position, cashflow, readiness, idempotency, commit, replay, and whole-transaction work
to be compared without retaining portfolio or transaction identifiers. A certifying run fails when
the scrape is unavailable or contains no bounded samples; an interrupted run still writes the
failure beside all other partial evidence. Cumulative and mean durations are attribution evidence,
not latency percentiles or service-level objectives.

The same runtime scrape retains existing cost-processing execution counts by bounded mode/method,
plus recalculation duration, recalculation depth, and restored-open-lot histogram count/sum/mean.
This separates pure calculation and replay depth from the wider cost stage before database,
persistence, or coordination changes are proposed. Complete certifying runs require execution,
recalculation-duration, and recalculation-depth samples. An empty restored-lot set is valid for a
workload containing only initial opening lots.

The drain loop also fails fast on an atomicity contradiction instead of waiting for its full
timeout. Once every expected transaction is durable, no valuation job remains pending or
processing, and the durable outbox is empty, each `COMPLETE` valuation job must have a matching
snapshot for the same portfolio, security, valuation date, and epoch. A completed job without that
snapshot is terminal diagnostic evidence: no queued work remains that can repair it. Retain the
reported count, worker lost-ownership logs, job attempt counts, processed-event fences, and Kafka
lag; do not classify the run as capacity evidence or raise the timeout.

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

The exact-source certifying fan-in run `20260715T100128Z` proved the one-portfolio x 1,000-position
shape. It produced exact transaction/snapshot/position counts and one reconciled portfolio row,
closed both durable queues, and reported zero service-log errors. Valuation-to-position
p50/p95/p99/max was `2.895919s`/`5.6004667s`/`8.03734857s`/`8.410595s`; portfolio aggregation
completed in `1.723829s`. Across 33 complete resource samples, peaks were 24 database connections,
three active connections, four idle-in-transaction connections, zero lock waiters, zero blocked
sessions, `77.05%` combined-runtime CPU, and `92,148,858` bytes memory.

For completed runs that already converged, use
`python scripts/operations/bank_day_load_reconciliation_report.py --run-id <run_id> --business-date <YYYY-MM-DD>`
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
