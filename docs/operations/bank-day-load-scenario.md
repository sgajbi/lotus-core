# Bank-Day Load Scenario

This runbook defines the governed `lotus-core` load scenario for a realistic
average banking day:

1. `100` portfolios,
2. `100` BUY transactions per portfolio,
3. `10,000` transactions total,
4. deterministic instrument, FX, and market-price support data,
5. end-to-end proof across ingestion, asynchronous processing, query APIs,
   reconciliation, health, and logs.

## Purpose

Use this scenario to answer customer-grade questions:

1. how long does `lotus-core` take to ingest and process a normal day,
2. when do query and support APIs become accurate and ready,
3. whether positions, valuations, and timeseries reconcile exactly,
4. whether worker health, backlog, and logs remain operationally clean.

## Current Evidence Posture

Clean exact-source daily artifact `20260811T161351Z-bank-day-load.json` is a valid
certifying-shape capacity failure. It made all `100,000` transactions durable and reconciled all
`1,031` database resource samples with zero unattributed clients, but only `95,873` valuation
snapshots and `95,865` position-timeseries rows completed before the fixed drain deadline. This
proves the service-attribution classifier while leaving the capacity profile unapproved. It is
retained as historical diagnostic evidence and must not be rerun merely to reproduce the same
limit. The owner-approved current acceptance target is the bounded `10,000`-transaction profile
below. Issues
`#794` and `#795` remain open; do not increase beyond 12 transaction partitions, add aggregation
debounce, or restore rejected position-lock/MAX experiments without new evidence. A final-head
daily run and the governed recovery, correction, and restatement profiles remain required.

## Automation

Run:

```powershell
python scripts\operations\bank_day_load_scenario.py `
  --compose-project-name lotus-core-app-local `
  --portfolio-count 100 `
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

`daily` is the bounded 100-portfolio x 100-position profile. `fan-in` is the certifying
one-portfolio x 1,000-position aggregation profile. `price-burst` first materializes 100 portfolios
x 100 shared instruments, then applies a 5% same-date price correction and requires all 10,000
snapshots and position rows plus 100 portfolio rows to carry post-correction timestamps and exact
corrected values. The smoke target is always recorded as
`evidence_classification=diagnostic`; it validates orchestration but cannot certify capacity or
close a #714 workload requirement. Certifying profiles fail fast unless `--build` is active, and
the repo-native profile targets supply it, so existing/stale local images cannot emit certifying
evidence.

Dispatcher capacity is governed once in
`docs/standards/outbox-capacity-profile.v1.json`. Run
`make outbox-capacity-profile-guard` to prove that development, CI, and the consolidated production
deployments use the same candidate `1s` poll, `1000` row batch, `130s` claim lease, `150s`
termination grace, and unchanged three-attempt retry ceiling. The guard cross-checks the Kafka
delivery fence and supervised shutdown safety bounds and rejects Compose/Kubernetes drift. The
profile remains `candidate_pending_exact_source` until its current-source 10,000-transaction run
passes; do not describe the configuration as certified or tune it independently in one environment
before that receipt exists.
Run `make test-outbox-capacity-acceptance` to execute the contract's deduplicated direct PostgreSQL
failure-mode nodes and its managed dispatcher-restart gate without reconstructing commands by hand.
Certifying evidence also requires monotonic recent publication-age p50/p95/p99, an observed
processed-event throughput window, exact pending/retry/failed/topic totals, and count-reconciled
producer cohorts; the newest 10,000 rows bound only the publication-age percentile sample.
The monitor reads those totals, the bounded age sample, and topic cohorts in one PostgreSQL
statement snapshot so live dispatcher progress cannot produce internally contradictory terminal
evidence.

The managed profile is the sole database and resource sampler during a certifying run. Monitor a
background execution through its governed task status, owned-container liveness, and terminal
artifact; do not add ad hoc `docker exec` row counts, full-table database queries, a second Compose
build/test, or another Docker-heavy workload. Those observations consume the same database, CPU,
I/O, and connection capacity being measured. If a bounded read-only diagnostic query was executed,
record it with the run. A passing run may be retained as conservative acceptance evidence because
the observer only added load, but its timing is not the clean comparison baseline. A failed or
timed-out run cannot support a capacity verdict until repeated without the external observer.

Service readiness and seed materialization use separate deadlines. Readiness remains a short
startup check, while certifying profiles allow up to 600 seconds for source records to become
durable before transaction submission. Seed timeout failures remain hard failures and do not
weaken the downstream drain or reconciliation deadlines.

The certifying fixture is source-first. It persists portfolios, instruments, FX rates, and market
prices; waits for both source rows and the FX/price consumer idempotency fences; then publishes and
waits for the business-date horizon before submitting transactions. This ordering keeps initial
reference facts distinct from corrections. Activating the business horizon before the source
consumers drain can leave correction/reprocessing state that later rearms otherwise normal
transaction readiness and invalidates attempt-count evidence.

Current-business-date FX and market-price seed facts do not create replay merely because positions
have not been submitted yet. Later transaction processing emits authoritative valuation readiness
and reads those committed source facts. A delayed current-price notification queues source-correction
work whenever the same-day snapshot is absent, not current, price/currency-mismatched, or older than the
source; write timestamps alone never prove that a snapshot consumed that price. Backdated and
future source facts still require durable replay. A
daily run that creates materially more valuation-snapshot events than source position keys must be
investigated as work amplification rather than accepted by extending the drain deadline. Capacity
evidence retains exact topic totals plus bounded `(producer aggregate type, topic, count)` cohorts
for created and pending rows. Certifying reports reject absent cohort attribution and any cohort
total that diverges from topic or final status totals. These are domain-level diagnostic dimensions;
portfolio, security, transaction, correlation, claim, and other business identifiers must not
become metric or capacity-report dimensions.
Likewise, a normal valuation job should have one claim and one completion transition in its
attempt count. Jobs with repeated normal-lifecycle transitions indicate duplicate scheduling or
rearm amplification. Different correlation ids are lineage evidence only and must not reopen
completed work; only a freshness-proven source correction can request explicit rearm.
When repeats occur, the receipt retains at most 25 synthetic job samples with correction and
correlation lineage. Use them to identify the trigger family; the bound is diagnostic and must not
be widened into an unbounded business-identifier export.

`price-restatement` applies the same price correction across five business dates.
`fx-restatement` uses two governed business dates over the same 100 x 100 shape. The opening date
establishes transaction cost and position history with complete FX. The final date deliberately
withholds only `EUR/USD` and proves that affected jobs fail with the exact-date reason, affected
snapshots publish no market value or P&L, unaffected currencies still value, and no affected or
portfolio timeseries is published. The profile then ingests that exact-date rate while valuation
orchestration is stopped and proves restart recovery, one source observation, pair/date-bounded
revaluation, unchanged prior-date snapshots, exact market-value and unrealized price/FX/total P&L,
closed queues, clean reconciliation, and complete resource samples. This is a missing-source
recovery proof; it does not claim carry-forward FX authority or an open-ended historical sweep.
Price and FX corrections intentionally remain separate profiles so one cannot mask the other's
scope or timing.

## Scenario Design

The script:

1. waits for ingestion, query, control-plane, event-replay, and reconciliation
   services to become ready,
2. seeds portfolios, instruments, FX rates, and market prices through public ingestion APIs,
3. waits for source rows and the FX/price consumer fences to become durable,
4. publishes the business-date horizon last and waits for it to become durable,
5. ingests deterministic BUY transactions in batches,
6. monitors event-replay health during processing,
7. waits for position snapshots, security-level position timeseries, and
   portfolio-level timeseries to converge,
8. samples downstream APIs,
9. runs reconciliation checks for sampled portfolios,
10. inspects stable Compose service logs for real error lines using the configured project/file,
11. writes a machine-readable and human-readable evidence pack.

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
10. peak PostgreSQL connection utilization, active, idle-in-transaction, and open-transaction
    connections, lock waiters, and blocked sessions sampled during the workload, both in aggregate
    and across a fixed allowlist of service and operator-tool `application_name` cohorts,
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
command output or connection details. Certifying evidence fails when any sample attempt errors, when
any aggregate total, active, idle-in-transaction, open-transaction, lock-waiter, or blocked-session
count does not equal the sum of its bounded cohorts, or when an unattributed, ungoverned, or
local/test client identity is observed. PostgreSQL non-client workers are reported separately as
`postgres-background`; they are not attributed to an application service.

Standalone maintenance, audit, recovery, capacity, and release-rehearsal processes use fixed
process identities from the same bounded inventory. They must create engines through
`portfolio_common.db` or establish the validated tool identity before a shared lazy engine is
created. Request, worker, pod, portfolio, security, transaction, correlation, and claim identifiers
must never become PostgreSQL application names.

Before the managed stack is torn down, the scenario scrapes the combined transaction-runtime
metrics endpoint once and records one bounded entry per `stage` and `outcome`. Each entry contains
the operation counter, duration observation count, cumulative duration, and mean duration. This
allows cost, position, cashflow, readiness, idempotency, commit, replay, and whole-transaction work
to be compared without retaining portfolio or transaction identifiers. A certifying run fails when
the scrape is unavailable or contains no bounded samples; an interrupted run still writes the
failure beside all other partial evidence. Cumulative and mean durations are attribution evidence,
not latency percentiles or service-level objectives.

The same terminal collection scrapes bounded database-operation histograms from transaction
processing, valuation orchestration, position valuation, and portfolio derived-state runtimes.
Every retained repository/method sample carries its stable runtime identity. A certifying run fails
closed when the required hot-path sample for any runtime is absent, so transaction persistence,
valuation fan-out, snapshot materialization, position continuity, and portfolio aggregation cannot
be conflated in one process-wide total. The evidence retains no SQL text, parameters, connection
URLs, or business identifiers; it is causal profiling evidence, not a capacity pass by itself.

The same runtime scrape retains existing cost-processing execution counts by bounded mode/method,
plus recalculation duration, recalculation depth, and restored-open-lot histogram count/sum/mean.
This separates pure calculation and replay depth from the wider cost stage before database,
persistence, or coordination changes are proposed. Complete certifying runs require execution,
recalculation-duration, and recalculation-depth samples. An empty restored-lot set is valid for a
workload containing only initial opening lots.

The artifact retains each runtime's existing `db_operation_latency_seconds` histogram as one
deterministically sorted entry per bounded `runtime`, `repository`, and `method`. Each entry
contains an observation count, cumulative duration, and mean duration. Query text, SQL parameters,
portfolio, security, account, and transaction identifiers are not collected. Use these totals to
select a targeted persistence or coordination investigation; they must not be treated as a latency
percentile, an SLO, or proof that a particular resource is saturated.

The drain loop also fails fast on an atomicity contradiction instead of waiting for its full
timeout. Once every expected transaction is durable, no valuation job remains pending or
processing, and the durable outbox is empty, each `COMPLETE` valuation job must have a matching
snapshot for the same portfolio, security, valuation date, and epoch. A completed job without that
snapshot is terminal diagnostic evidence: no queued work remains that can repair it. Retain the
reported count, worker lost-ownership logs, job attempt counts, processed-event fences, and Kafka
lag; do not classify the run as capacity evidence or raise the timeout.

Exact clean fan-in `20260717T180631Z` demonstrated why this check is fail-closed: all 1,000
transactions and valuation jobs were terminal with attempts `2/2`, no repeats, and an empty
pending/failed outbox, but no matching snapshot or timeseries rows existed. The guard stopped the
run in `314.102s`. A prior exact run had converged, so preserve both results and diagnose the worker
ownership transition; do not infer a capacity limit or change lock ordering from the terminal
counts alone.

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

### Performance-load source completion diagnostics

Oversized diagnostic receipts retain admitted public probes through bounded sample compaction.
The child reserves metadata space inside the existing 32KiB output cap; the parent independently
bounds the receipt after adding original timing and cleanup, including a final custody reserve.
Already-redacted statement previews may be shortened with explicit truncation and original-byte
metadata. Sample tails may be omitted with original/retained/omitted row counts and retained
row refusal controls. Admission counts, probe statuses/reasons, scope and worker birth/generation
remain distinct from retained sample detail. Unknown probes or an irreducible envelope are
explicit byte-budget refusals; unavailable evidence is not zero or successful completion.
Compaction neither relaxes admission/redaction nor proves the financial timeout cause. The
20-row, six-second collection and enforcing drain/SLO budgets remain unchanged.

Phase join measurements preserve a safe rejected-active projection, not an alternate admission
path. `processing_phases.admission.rejected_active` contains at most20 identity/phase records with
the original first-refusal reason and `authority=not_admitted_not_causal`. Backend identity is
the full PID, timezone-qualified backend birth and database OID. Run generation remains distinct
from each delivery's row generation. Only validated worker/task identities, salted hashes,
allowlisted phase names and finite nonnegative worker monotonic times are retained; missing or
invalid values have explicit status and null value. Raw rejected input, SQL, bodies and business
identifiers are never exported. Supporting same-PID birth/database mismatch and full-key match
counts describe the original bounded sample, not database-wide absence or financial causes.

`runtime_db_waits.original_sample` preserves the pre-compaction identity-only vector used by
admission. The existing query is unchanged: current database, supported applications or their
blockers, transaction-start ordering and SQL LIMIT20. Coverage beyond that SQL limit is unknown.
`sampling_interval` measures that query's execute/fetch interval; `transport_interval` measures
the later phase-file read. `snapshot_timing` retains the worker's capture wall and monotonic
times; `snapshot_identity` retains its validated run generation and worker PID separately from
rejected-row worker/task identities. Collector and worker monotonic clocks are not interchangeable;
periodic snapshot publication and wall-clock uncertainty prevent an atomic active-at-query claim. Wall-clock
regression is explicit. Snapshot timing never supplies a new admission rule or an exact await.

Identity and rejected-candidate detail can itself be compacted. Inspect `detail_status` and
`byte_budget_coverage` before attempting a join: partial detail is unavailable for omitted keys,
not a negative match or authority to select by PID alone. Admission counts/refusals remain intact.
The outer32768-byte cap, child30720-byte reserve,20-row collections, six-second capture and
independent180-second full-profile SLO remain fixed. There are no extra queries, wider samples,
emitter/cadence changes or financial lock, epoch, tenant or economic changes. These measurements
do not retrospectively reconstruct identities missing from earlier receipts or qualify main.

Fee-source qualification examines the complete original cost/raw authority before requesting
retained processing receipts. Only an explicit absence of qualified original authority admits
the scoped receipt lookup; conflicting raw sources, malformed fees and ambiguous authority still
refuse the complete batch before publication. Malformed named-cost signatures now produce the
typed `TRANSACTION_REPLAY_SOURCE_INVALID` refusal with failed transaction IDs, rather than
leaking a model-validation exception from eager correction preparation. Existing tenant/source-FX
checks, None/zero distinctions, canonical serialization and source read locks are retained.
Original preparation is batch-local and reused across receipt awaits only while captured inputs
remain unchanged. This reduces unnecessary preparation/query work; it does not certify load SLOs
or establish the cause of a historical idle transaction or portfolio wait chain.

### Original Raw-Source Lookup Index

The bounded raw-source query retains every original row, including duplicates and late
contradictions, in outbox-ID order. Its non-unique partial index
`ix_outbox_events_raw_transaction_source` covers `aggregate_id`,
`CAST(payload ->> 'transaction_id' AS VARCHAR)` and `id`, restricted to
`RawTransaction`/`RawTransactionPersisted`. Fixed code-owned family selectors and the JSON key
are SQL literals; requested IDs and portfolio scopes remain bound parameters. There is no
latest-row selection, deduplication, limit, forced planner path or financial-policy shortcut.
The existing optional source `FOR SHARE`, canonical currency/fee validation and complete-UOW
rollback remain enforced.

Migration `c180b2c3d541` builds and drops the index concurrently. A valid expected index is
reused; an interrupted invalid/not-ready index on the owning table is rebuilt. A foreign-table
or valid unexpected same-name catalog shape fails closed and requires owner disposition; do
not drop foreign indexes or waive shape checks. Retain the migration exit and exact catalog
evidence when diagnosing a cutover. Local lookup plans, timings and writer-cost observations
do not qualify whole-loader capacity, ordering or the independent full-load SLOs in #795/#730.

The separate `make test-performance-load-gate-full` gate retains JSON/Markdown reports in
`output/task-runs/` when source completion raises, including profiles already evaluated and the
active failure stage. `completion_evidence` records each HTTP202 batch's independently submitted
transaction IDs/counts and supported job/correlation acknowledgement fields. A missing
acknowledgement is unavailable, not zero. Replay storm is explicitly not run when its source
admission fails. Report errors do not replace the original enforcing exception; a report error
after an otherwise successful run remains nonzero.

At a source timeout, deadline raw/cost/cashflow/position counts remain distinct from portfolio
aggregate claims. The latter can include older profiles and cannot certify the current prefix.
Additional observations occur after the drain deadline and do not relax the 240-second window,
independent profile SLOs, 640-record burst, 120-record replay source, 20-security shape or economics.

Diagnostics require the managed isolated runtime and matching database/PTP endpoints. The
collector in `scripts/operations/performance/load_completion_diagnostics.py` owns these probes.
Its separate owned process has a six-second response budget and bounded stop/reap attempts (two 0.2-second
joins). Its absence is reported as stopped/not-started or unconfirmed; cleanup errors remain
diagnostic evidence and never replace the load failure. Read-only PostgreSQL uses the shared
database factory with the existing `performance-load-gate` identity and `NullPool`: a supported
two-second connect limit, 500ms statement limit and 100ms lock limit. Profile limits are scoped to
the private diagnostic child; inherited URL/security validation is retained. The owned connection
and engine are closed/disposed on success and failure. It validates governed tenant ownership
and returns at most20 rows per probe. It captures exact submitted-ID outcomes, ingestion-job and
outbox lifecycle counts/oldest ages, supported DLQ/failure reason codes, and isolated-runtime
wait/blocker identities. It excludes raw SQL text, payloads, credentials and unrelated business
rows. Only whitelisted SQL grammar/schema structure is exported; literals, parameters, unknown
identifiers and numbers are redacted. Comments, dollar quotes, escapes, ambiguous quotes and
truncated statements are refused rather than parsed heuristically.

### Replay Completion Evidence

`completion_evidence.replay_completion` retains the baseline scrape, accepted-count sum,
derived target and final polling observation. Scrapes include timestamp, status, the existing
processed-transaction metric and bounded stage/outcome labels. A missing sample is not measured
zero. Invalid, ambiguous or oversized samples cannot satisfy completion; an observed counter
decrease or changed counter/process-birth identity prevents later larger counts from hiding a reset.
The same scrape must expose a single finite `process_start_time_seconds` birth observation;
missing or changed producer birth prevents successful continuity, even with unchanged labels and
larger counts. The worker runtime serves metrics and consumer tasks in the same Python process;
this binds observations to that endpoint's producer, not a guessed database or container PID.
Completion scrape input has an independent streamed 1MiB bound for the combined HTTP/DB/Kafka
histogram exposition, distinct from the collector's 32KiB projected-output limit. Synthetic
larger-than-32KiB valid exposition is unit-tested; actual deployment exposition size remains
a runtime validation requirement. Exhaustion is unavailable evidence, not completion.
Missing counter-creation metadata remains `MISSING`, not a verified worker lifetime. The existing
240-second observation deadline and independent full-profile 180-second SLO remain unchanged.

At the first continuity-qualified poll at or beyond the profile SLO, an unmet replay target
requests one active diagnostic capture. The completion check comes first: a target already
observed as complete does not capture drained state, even when its finite elapsed time breaches
the SLO. Missing/reset producer continuity cannot request an active snapshot. The retained
`slo_boundary_capture` records the observed count/birth, request elapsed time and lateness;
later completion or timeout cannot replace this earlier evidence. An unavailable request still
counts as the one attempt. Without an active attempt, the existing timeout diagnostic remains.

Capture uses the same managed, private, birth-qualified probes and unchanged 32KiB/20-row,
120-second enable-age and 500ms I/O bounds. A finite owned receiver drains its child pipe while
completion polling continues; a separate owned deadline timer stops the child independently of
late report finalization, reserving cleanup time within the six-second request/collection policy.
Before all profile workloads and measured clocks, the owned child is prepared idle with a
readiness receipt. After replay submissions and before waiting, a publish-once private32KiB
input slot binds actual source IDs and only present acknowledgement job IDs. Accepted delivery
IDs remain missing when acknowledgements contain only counts. Missing, oversized, malformed,
foreign or expired scope is unavailable, never an observed zero from empty-ID workload queries.
The callback records the boundary, writes only a fixed-size immutable parent-deadline header,
and signals the existing Event; it never serializes scope, spawns, receives or joins. The child
validates descriptor/version/bounds/run/tenant/portfolio/stage, copies and closes its attachment
before probes, and cannot restart its budget after late scheduling. Input and output each have
separate32KiB caps; parent cleanup closes/unlinks the private slot without publishing its name,
payload or IDs. Native `Process.start()` has no hard preparation latency bound,
so actual setup time is reported separately, not certified as a startup SLO. Preparation expiry
or failure is unavailable, not retried. A separate finite idle allowance derives from existing
batch/sleep/drain limits plus pre-boundary health requests using their configured timeout.
Current profiles have five health snapshots, each three sequential requests at20s:300s nominal
allowance. Requests timeouts are not full-response wall-clock bounds; this arithmetic is not a
hard scheduling/runtime guarantee and extends no enforcing deadline. Idle expiry/cancellation and
unused teardown prevent probes and do not manufacture active capture evidence. Both workers are joined
before runtime teardown. A partial/oversized frame, child failure or unavailable cleanup is
explicit evidence, not measured zero. No diagnostic callback or finalization exception replaces
the original completion result, timeout or enforcing failure.

Request time is not exact capture time. Launch overhead, request-to-child wall-clock delay when
available, scope-binding/fixed-header overhead, custody elapsed time and cleanup status are
retained; missing timing remains null.
Scheduling and probe latency can make observation late. The capture is supporting evidence,
not an exact 180-second atomic snapshot, delivery receipt, Python await or financial cause proof.
Completion polling, workload, ordering, UOW/outbox behavior and the independent SLO verdict are
unchanged: a completed 213-second full replay still fails the 180-second limit.

Ordered replay submissions and supported job/correlation/request/trace acknowledgements are
retained per request. Partial `accepted_count` is count-only evidence: accepted IDs and per-ID
durable completion receipts remain `MISSING`. Repeated submitted IDs retain their submission
order; a conflict is not an accepted batch. Transport or malformed acknowledgement refusal keeps
the attempted submission without exporting private response or error text.

On replay timeout, the existing bounded collector runs once after the completion measurement;
diagnostics cannot improve the failed verdict or add time to the measured completion. Portfolio
rows, fences and outbox records may predate this replay and are not its durable receipts. PostgreSQL
wait/lock observations bind PID to `backend_start` and retain database/relation OIDs, including
NULL relation for transaction-ID locks; NULL is not a causal table attribution. The collector
observes the exact managed service container ID, creation/start timestamps and container-init
PID, using plain Docker label-filtered `ps` (no Compose plugin child), followed by exact
project/service/published-port inspect verification. Container-init PID is not an observed
application worker PID. Application-worker PID and exact Python await remain `MISSING` unless independently
measured. This snapshot alone cannot establish a restart history or the cause of a load failure.

The existing PTP metrics interface provides bounded runtime inflight/backlog/cached-lag samples;
these are not prefix-level completion. Broker reads sample at most10 partitions per raw/persisted
topic using existing group committed offsets and low/end watermarks, without joining a consumer
group, storing offsets, committing or creating topics. Shared Kafka connection policy supplies
validated transport credentials and trust; invalid security yields unavailable evidence before
client construction. Sampling is not a whole-topic proof.
Metrics I/O and broker calls have 500ms timeouts. Metrics input and diagnostic output each have a
32KiB byte limit; JSON reports have a 256KiB limit. Missing interfaces/permissions, exceeded
budgets and probe failures are explicitly unavailable/exhausted rather than zero or passing.
The current actual PTP exposition size remains a runtime validation requirement; a byte-budget
result is not consumer evidence. These diagnostics support investigation, not a causal assertion,
financial fix, throughput certification or accepted main.

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
