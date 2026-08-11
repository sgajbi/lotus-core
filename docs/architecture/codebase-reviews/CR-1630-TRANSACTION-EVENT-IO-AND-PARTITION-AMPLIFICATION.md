# Transaction Event I/O And Partition Amplification

## Objective

Remove measured transaction-event I/O and partitioning bottlenecks without weakening transaction
ordering, idempotency, atomic outbox delivery, corporate-action correctness, or downstream event
contracts.

## Finding

The exact 100,000-transaction daily profile
`output/task-runs/20260716T153249Z-bank-day-load.json` reached the fixed two-hour deadline with
`99,314` durable transactions and `96,438` completed valuation jobs/snapshots. Valuation
amplification was already removed: completed jobs had attempt count `2/2`, repeated-processing
count was `0`, and failed outbox/DLQ counts were `0`.

The remaining path still performed unnecessary I/O:

1. every outbox event was explicitly flushed before the surrounding transaction commit even though
   no caller needed the generated database id before commit;
2. routine per-record success details were emitted at `INFO` across transaction persistence,
   transaction economics, cashflow, valuation, outbox, and position-timeseries materialization;
3. `transactions.raw.received` and `transactions.persisted` used `portfolio_id`, serializing every
   independent security in one portfolio through one Kafka partition.

The first certifying fan-in run
`output/task-runs/20260716T175742Z-bank-day-load.json` proved the partition impact. One portfolio
with 1,000 independent securities reconciled correctly but required `1,452.71s`, including
`1,247.665s` of drain time. Because new position rows arrived slowly, portfolio aggregation was
rearmed and completed `525` times for one final portfolio-day row.

## Implemented Direction

1. Outbox staging adds the event to the caller-owned SQLAlchemy transaction and relies on the normal
   commit flush. Dispatcher visibility remains atomic because uncommitted rows are not visible.
2. Routine per-record success logs use `DEBUG`; bounded metrics and all warning, retry, failure,
   stale-state, reconciliation, and lifecycle logs retain their operational levels.
3. The structured-log guard scans the governed hot paths and rejects known high-volume routine
   messages at `INFO`.
4. Transaction ingestion, raw persistence outbox, and repair replay use one shared key policy.
   Unlinked transactions use `portfolio_id|security_id`; a non-blank linked group uses
   `portfolio_id|transaction-group|linked_transaction_group_id`.
5. Dates and epochs remain outside the key. Unlinked flows preserve one position stream across
   normal, duplicate, backdated, reversal, correction, and restatement processing. Linked
   cross-security legs share the portfolio/group stream and retain their canonical producer order.
6. Dependency references, deterministic domain ordering/rebuild, reconciliation, and
   portfolio-security database locks remain mandatory for corporate-action correctness. The linked
   group key prevents cross-partition reordering; it does not replace those controls or introduce
   portfolio-wide Kafka serialization.
7. Normal cashflow persistence uses one PostgreSQL conflict-aware insert instead of a savepoint,
   flush, and refresh sequence; duplicate delivery still returns the authoritative stored row.
8. Position-history writes and outbox rows rely on the caller-owned unit-of-work commit instead of
   eager flushes that no caller observes.
9. Residual per-record success logs in reference persistence, Kafka delivery callbacks, outbox
   batches, position locking/deletion, and non-cash FX handling use `DEBUG`. The guard scans every
   persistence repository and rejects the governed messages at `INFO`.
10. Position materialization progress is one typed application-port value loaded by one SQL
    statement. Separate history-date and completed-snapshot-date methods and round trips were
    removed.
11. The two transaction topics and their live consumer groups use twelve partitions/in-flight
    tasks. Same-position concurrency remains one; unrelated topic capacities are unchanged.
12. Cost-basis processing and AVCO rebuild load portfolio policy plus optional instrument facts
    through one typed application-port bundle and one SQL statement. Missing portfolio and missing
    instrument behavior remain distinct; no calculation or retry contract changed.
13. Retained workload artifacts record the emitting Git revision and a non-sensitive clean, dirty,
    or unavailable tree state. Local evidence remains subordinate to trusted CI and deployment
    receipts even when its source revision is present.
14. Governed bank-day artifacts scrape the existing combined-runtime Prometheus metrics before
    teardown and retain bounded count, duration count, cumulative duration, and mean duration by
    transaction-processing stage/outcome. Complete certifying runs fail closed when this evidence
    is absent.
15. The same scrape retains existing cost execution mode/method counts, recalculation duration and
    depth, and restored-open-lot observations. This adds internal cost attribution without adding a
    production metric or changing calculation behavior.
16. Position materialization exposes its current epoch to the following cashflow stage only after
    generation rearm conditionally updates the position-state row for that exact expected epoch
    and holds the resulting write lock inside the shared unit of work. Cashflow applies the existing
    epoch rule from that proven lock-scoped value instead of loading the same position state again.
    A concurrently advanced epoch makes the conditional update affect zero rows, so no epoch is
    exposed and cashflow falls back to the database-backed fence. No-record, stale, coalesced, and
    unsuccessful-rearm paths retain the same fallback.
17. `BaseConsumer` retains a failed record and retries it in process under the same partition
    ordering key instead of assuming an uncommitted offset will be redelivered in the same consumer
    session when either governed attempt/elapsed budget is positive. Default-zero keeps the
    compatibility posture: one processing attempt, no in-process sleep or DLQ transition, and an
    uncommitted offset for redelivery after restart or rebalance. It also stops the consumer before
    a later same-partition offset can be processed or committed and discards already queued records
    for that partition. Terminal recovery separately retries DLQ publication and the post-DLQ
    commit without rerunning business processing or republishing an already confirmed DLQ record.
18. Transaction valuation readiness treats each durable outbox event as a distinct source mutation.
    A positive `outbox_id` header requests processing, but only the maximum committed positive ID
    observed by the exact-scope valuation claim advances the durable watermark. A newer ID may rearm
    a completed natural-key job or request requeue when a different mutation arrives during
    processing; transport input cannot initialize or advance claimed authority. Exact payload
    identity keeps same-outbox redelivery non-disruptive. Truly headerless compatibility records
    keep the prior non-rearming behavior, while malformed or nonpositive present sequences fail
    closed before idempotency. The readiness payload, schema version, topic, partition key, and
    consumer group remain unchanged.
19. Canonical clean bootstrap persists FX and market-price histories before activating the governed
    business-date horizon and fails closed until each required source window is query visible.
    Price and FX observations received before any horizon are bootstrap facts rather than late
    corrections; transaction-owned readiness performs the first valuation after calendar
    activation. Backdated and future observations against an existing horizon keep correction
    replay semantics.
20. The aligned raw/persisted market-price topics and their live consumer groups use twelve
    partitions/in-flight tasks. The producer pins librdkafka's stable CRC32 keyed partitioner.
    Security ordering is unchanged; the canonical ten-key maximum lane falls from five series
    (`1,880` facts) at eight partitions to three (`1,128` facts) at twelve.
21. The performance load gate uses one stable portfolio and twenty stable security keys whose
    governed CRC32 distribution places at most two keys on each of the twelve transaction
    partitions. Each run starts after the latest persisted timestamp for that governed portfolio,
    then transaction timestamps increase by one microsecond across steady, burst, and replay source
    phases. Clean and supported reused-stack runs therefore measure append processing instead of
    accidentally turning later phases or runs into retroactive history. Repair replay remains
    intentional. HTTP
    `409` replay blocks contribute zero expected completions, while `202` responses contribute only
    their validated `accepted_count`. The observation window is separate from, and longer than,
    the unchanged profile SLOs so a failure report can retain final domain-count diagnostics.
22. Release rehearsal manifests may provide only the six governed, non-secret build metadata
    values consumed by `/version`. Database URLs, ports, Compose controls, and arbitrary environment
    overrides are rejected before runtime preparation; image digest and service image overrides
    remain adapter-owned.
23. Transaction release and interruption-recovery gates measure DLQ growth from the durable
    `consumer_dlq_events` ledger, scoped to the exact transaction consumer group and source topic.
    Standard readiness remains readiness evidence only and cannot silently fabricate a zero DLQ
    baseline when a field is absent.
24. Initial-opening cost persistence applies the same canonical transaction-control-code policy as
    aggregate selection, so case and surrounding whitespace cannot route a valid BUY into a later
    case-sensitive rejection. The atomic repository also rejects mismatched portfolio, security,
    or transaction/checkpoint identities before constructing or executing SQL. `TRANSFER_IN`
    remains on the generic opening-lot path and all public transaction contracts are unchanged.
25. Valuation readiness accepts at most one `outbox_id` header. Duplicate header keys are rejected
    before idempotency regardless of value or order, preventing Kafka header ordering from choosing
    which source authority is trusted. Headerless compatibility and one valid positive sequence
    retain their existing behavior.
26. The governed database catalog now records every live valuation-job lifecycle and diagnostic
    column, including the default-zero exact-scope claimed readiness watermark. This is a truth
    reconciliation only; the underlying schema is unchanged in this slice.
27. Valuation jobs rotate a constrained opaque token on every claim. Internal dispatch carries the
    token as an additive Kafka header, and completion, failure, missing-reference, and no-position
    transitions require an exact match before snapshot/outbox side effects. Stale reset,
    supersession, terminal transition, and dispatch recovery clear ownership. A two-session
    PostgreSQL proof resets claim A, reclaims as B, rejects late A as `NOT_OWNED`, and permits B.
    Migration `c151b2c3d518` adds the nullable rolling-compatibility column and check constraint;
    the public event payload, schema version, topic, and partition key remain unchanged.

## 2026-08-10 Certification Task Reconciliation

- Task `eng-task-20260810-145143-lotus-core-certification-make-profile-derived-state-daily`
  is diagnostic only because Agent 1 breached its observation fence. Its terminal artifact cannot
  certify or reject capacity; exact owned resources were verified absent after teardown.
- Clean rerun `eng-task-20260810-170501-lotus-core-certification-make-profile-derived-state-daily`
  was deliberately stopped after adversarial review exposed the unresolved valuation ownership
  defect owned by #487. The Platform ledger truth is `LOST`, not success or a capacity verdict.
  Only its verified process tree and Compose project
  `lotus-integration-derived-state-daily-workload-0f9e53a3` were stopped; verification found zero
  owned processes, containers, networks, and volumes.
- Certification must restart from the pushed corrected exact head after protected CI. Monitoring
  remains limited to the Platform ledger, process liveness, and terminal artifact.

## Measured Result

The rebuilt fan-in run
`output/task-runs/20260716T183314Z-bank-day-load.json` completed with:

- exact `1,000` transactions, completed jobs, snapshots, snapshot events, and position-timeseries
  rows;
- one final portfolio-timeseries row and exactly one aggregation-completed event;
- valuation attempt count `2/2`, repeated-processing count `0`;
- final pending/failed outbox `0/0`;
- `311.457s` total duration and `110.302s` drain time;
- no failed evidence checks.

Compared with the portfolio-key baseline:

- total duration reduced `78.56%`;
- drain time reduced `91.16%`;
- repeated aggregation completions reduced from `525` to `1`.

No aggregation debounce was added. The repeated aggregation was downstream evidence of serialized
upstream arrival and disappeared after the domain-correct partition fix. Adding a timer after that
result would increase freshness latency without a remaining measured defect.

Subsequent bounded evidence kept measurement claims conservative:

- clean canonical source-first diagnostic at `73fa4ada3` proved the new fence but exposed exact
  CRC32 key skew: partition 4 owned five of ten price series and `1,880/3,760` raw facts. The
  measured ordered lane threatened the unchanged 900-second source-readiness budget. Twelve
  partitions spread the same keys across seven lanes and reduce maximum serial work `40%`; final
  canonical pass evidence remains required before closure;

- cashflow persistence fan-in `20260716T205744Z` completed exactly with `105.245s` drain;
- deferred position-history flush fan-in `20260716T231755Z` completed exactly with `105.234s`
  drain, effectively unchanged, so the benefit is unit-of-work simplification rather than a claimed
  throughput gain;
- two attempts to skip first-position delete/anchor reads were rejected and fully reverted. Moving
  the lock earlier increased drain to `115.253s`; a concurrency-safe post-lock `MAX` recheck
  increased it to `110.252s`. The latter aggregate query cost more than the empty delete plus
  indexed anchor read it replaced;
- residual hot-path log suppression fan-in `20260717T000106Z` completed with exact `1,000`
  transaction/job/snapshot/position rows, one portfolio row, attempts `2/2`, zero repeats, zero
  blocked sessions, and closed outbox queues. Its `110.256s` drain was unchanged from the
  immediately preceding run, so only the proven log-volume and operational-signal improvement is
  claimed.
- coalesced progress-read fan-in `20260717T001431Z` completed with exact reconciliation, attempts
  `2/2`, zero repeats, and closed queues. Drain was `110.249s` versus `110.256s` immediately prior,
  so the claimed improvement is the direct two-to-one port/query reduction and simpler ownership
  contract, not end-to-end throughput.
- transaction-only 12-way fan-in `20260717T003225Z` completed in `297.619s` with `95.247s`
  drain, a `13.61%` drain reduction from the 8-way `110.249s` run. It retained exact
  transaction/job/snapshot/timeseries reconciliation, attempts `2/2`, zero repeats and outbox
  failures, peak active database connections `11`, and peak lock waiters/blocked sessions `2/2`.

The post-cashflow exact daily run `20260716T210418Z` reached `96,511` completed jobs/snapshots at
the fixed deadline, up from `95,871` before that persistence change, but still did not satisfy the
100,000 exact-source acceptance criterion. Another exact daily run is not justified until bounded
evidence identifies a material remaining transaction-economics improvement.

The exact post-twelve-way daily run `20260717T092348Z` made all `100,000` source transactions
durable but reached only `83,644` complete valuation snapshots, `83,398` position-timeseries rows,
and `916` portfolio-timeseries rows before the fixed two-hour drain deadline. Valuation attempts
remained `2/2`, repeated-processing count remained `0`, and failed outbox count remained `0`.
Topic creation counts isolated the tail to transaction processing: `transactions.persisted`
reached `100,000`, while `transaction_processing.ready`, `transactions.cost.processed`,
`cashflows.calculated`, and `portfolio_security_day.valuation.ready` each reached `83,644`.
Downstream stages kept pace with the facts they received. This is valid capacity-failure evidence,
not infrastructure or outbox failure evidence. The failure artifact's `drain_seconds = 0` despite a
two-hour drain remains diagnostic debt under #730.

The later exact-head daily run `20260717T125841Z` is a second valid capacity failure, not an
external-kill diagnostic. It made all `100,000` source transactions durable and reached `82,014`
valuation snapshots, `81,959` position-timeseries rows, and `876` portfolio-timeseries rows before
the fixed drain deadline. `124` portfolios remained incomplete, with `21` valuation jobs and `15`
aggregation jobs open. Attempts remained `2/2`, repeats remained `0`, final outbox pending/failed
was `58/0`, and all eight governed service logs contained zero errors. Topic counts again tie the
remaining tail to transaction processing: `transactions.persisted` reached `100,000`, while cost,
cashflow, and valuation-ready topics each reached `82,014`; downstream snapshot persistence then
reached `81,973`. Peak database total/active connections were `55/19`, idle-in-transaction reached
`29`, and lock waiters/blocked sessions reached `8/8`. The run shared the host with the separately
owned 15-container canonical UI stack, so its `1,630`-snapshot / `1.95%` shortfall against
`20260717T092348Z` is not attributed to a code regression. The artifact hash is
`357B0B929F4170ADBF7EE91B9F4E9F733C7B3A16C2D04EEE36F1CC12316EF030`.

The cost-reference bundle passed exact same-host diagnostic A/B evidence under shared Docker load:
parent `349ee126c` drained in `125.478s`, while signed implementation `2d49fc8f1` drained in
`120.492s`, a `4.986s` / `3.97%` relative improvement with exact reconciliation. The result supports
retaining the direct two-to-one query reduction, but both runs remained materially slower than the
governed `95.247s` baseline. A concurrent actor changed only runner provenance/docs/tests/wiki
during the parent run, so the A/B result is attribution evidence rather than standalone
certification. It does not justify another 100,000-transaction daily run.

Two further statement-shape improvements are retained for their direct database-I/O and ownership
benefits, but their exact fan-in evidence is deliberately not presented as throughput improvement:

- signed commit `a3c9eeaac` changed position-state creation to `INSERT ... DO NOTHING RETURNING`,
  returning a newly created state directly while retaining the authoritative `SELECT` fallback for
  a concurrent conflict. The absent-key path fell from two statements to one. Exact fan-in
  `20260717T152820Z` completed and reconciled with `110.369s` drain, `4.65%` slower than the
  `105.470s` parent baseline;
- signed commit `b7e7e1be2` added an explicit initial-opening-lot persistence scope. A position with
  exactly one opening transaction skips the redundant complete-snapshot reread while still writing
  its AVCO pool checkpoint; existing and backdated timelines retain complete reconstruction. The
  ordinary first-BUY PostgreSQL statement shape fell from ten statements to nine. Exact fan-in
  `20260717T155339Z` completed and reconciled with `110.334s` drain, effectively neutral versus
  `110.369s` and `4.61%` slower than the `105.470s` parent baseline.

Neither result justifies another two-hour daily run. Further query-level micro-optimization on this
path is paused until full unit-of-work timing or equivalent evidence identifies a material
transaction-processing bottleneck.

The first stage-attributed certifying fan-in `20260717T162223Z` then completed at exact signed head
`20333978a` with exact 1,000 transaction/snapshot/position rows, one portfolio row, `110.416s`
drain, attempts `2/2`, repeats `0`, final outbox `0/0`, and zero failures. Across 1,000 successful
operations, the existing bounded metrics attributed whole-transaction duration as follows:

- cost `199.828910s` / `0.199828910s` mean (`37.18%`);
- idempotency `95.100972s` / `0.095100972s` mean (`17.69%`);
- position `93.364817s` / `0.093364817s` mean (`17.37%`);
- cashflow `63.015394s` / `0.063015394s` mean (`11.72%`);
- readiness `49.527981s` / `0.049527981s` mean (`9.21%`);
- commit `35.701706s` / `0.035701706s` mean (`6.64%`).

Whole-transaction duration was `537.486227s` / `0.537486227s` mean. Cost is therefore the largest
remaining stage, but this aggregate evidence does not yet identify a safe internal cost change or
justify another daily run. The next investigation must obtain bounded internal cost timing/query
evidence while preserving ordered append, full-rebuild fallback, method-specific lot state,
backdated/correction semantics, and single-writer coordination. Artifact SHA-256 is
`668AC265FA7D12058A1A917CFF1B8B1ED50B5AA9E492B2AE7255867A461A6E17`.

The next exact-source fan-in diagnostic at signed head `37abbf19b` separated calculator work from
the wider cost stage without adding production instrumentation. All `1,000` cost executions were
FIFO full rebuilds with recalculation depth exactly one. Pure recalculation duration totalled only
`0.18031266846810468s`, about `0.000180313s` per transaction, and no opening lots were restored.
The earlier `199.828910s` cost-stage total is therefore dominated by database, persistence, or
coordination work rather than cost arithmetic. No calculator change is justified by this evidence.

That diagnostic is not a capacity result. It reached a terminally inconsistent valuation state:
all `1,000` transactions, position-history rows, and position-state rows were durable; all `1,000`
valuation jobs were `COMPLETE` with attempt count `2`; the Kafka group had zero lag; and the worker
had recorded `1,000` processed-event fences. Nevertheless it emitted `1,000` lost-ownership
warnings and produced zero snapshots, snapshot outbox rows, or timeseries rows. Rollback-only
repository and full valuation-sequence probes returned successful ownership in isolation, so the
runtime contract was not changed on inference. Signed `6640ec911` instead makes the load gate fail
immediately when all expected transactions and outbox work are drained but a `COMPLETE` valuation
job lacks its atomic same-scope snapshot. This preserves the anomaly for diagnosis and prevents an
irrecoverable terminal state from consuming the full drain timeout.

The exact clean rerun `20260717T174251Z` at signed evidence head `d34da9305` completed normally,
so the terminal contradiction did not reproduce and the fail-fast predicate did not reject normal
convergence. The run reconciled exactly `1,000` transactions, valuation jobs, snapshots, and
position-timeseries rows to one portfolio row in `105.622s` drain, with attempts `2/2`, zero
repeated processing, zero open jobs, and final outbox pending/failed `0/0`. Pure FIFO recalculation
was again negligible: `0.160816s` total and `0.000160816s` mean at depth one, compared with
`194.163301s` for the wider cost stage. The next target must therefore be bounded database,
persistence, or coordination evidence, not calculator arithmetic. Artifact SHA-256 is
`5188E393806662464F97247072CB837B7E7EB97A3A455CD30F19D99813C3D524`.

The next exact clean fan-in `20260717T180631Z` at signed implementation head `37ffa2fad`
reproduced the terminal contradiction for the complete workload. All `1,000` transactions and
valuation jobs were durable, attempts remained `2/2`, repeated processing remained zero, and the
final pending/failed outbox was `0/0`; nevertheless snapshots and both timeseries stages remained
zero. The fail-fast guard ended the run in `314.102s` with
`completed_valuation_jobs_without_snapshots=1000`. This is reproducible runtime ownership evidence,
not a capacity result and not proof of an UPSERT or lock root cause. JSON SHA-256 is
`CEFF56A9AAA90D1D4F5852FDD707C7A356C17A0D59633FC736E9262B94005525`.

The additive database evidence retained eleven complete repository/method series totalling
`139.978303s`. The largest were `PositionStateRepository.get_or_create_state` (`2,000` calls,
`36.802742s`), cost-basis lock acquisition (`1,000`, `18.139104s`), position materialization
progress (`1,000`, `15.217857s`), and position history read/delete operations (`1,000` each,
`12.149594s` to `12.558317s`). FIFO recalculation still totalled only `0.152853s` at depth one.
Because these repository timings span cost, cashflow, position, and readiness work, their sum is
not a cost-stage percentage. It narrows the next work to targeted persistence/coordination and
valuation ownership-transition proof without justifying another broad micro-optimization.

The bounded ownership slice at signed head `45295cf24` replaced the ambiguous internal boolean
transition result with `TERMINAL_APPLIED`, `REQUEUED`, and `NOT_OWNED`. The valuation processor
continues to permit snapshot, outbox, and idempotency completion side effects only after
`TERMINAL_APPLIED`; it now records whether suppression was caused by newer source work or lost
ownership. The repository contract fails closed if PostgreSQL returns any unsupported applied
status. This is an internal application/repository diagnostic contract, not a public event or API
change.

Two consecutive exact clean certifying fan-in runs at that SHA completed without a requeue or
lost-ownership suppression. `20260717T193156Z` reconciled all `1,000` rows with `105.710s` drain,
attempts `2/2`, zero repeats, closed outbox, and seven aggregation completion facts.
`20260717T194013Z` repeated exact reconciliation with `95.645s` drain, attempts `2/2`, zero repeats,
closed outbox, zero lock waiters/blocked sessions, and exactly one aggregation completion fact.
Their JSON SHA-256 values are respectively
`47C1959D3E9113526BDA69AAA6D0F5C983861B9E8E725BCBABB8C5716AC5846A` and
`63179D93C8DEBABE00F1CE73049DA65153EB6A604F3749681D31DC8F0DA6FCF9`. Both managed teardowns
removed every run-owned resource and preserved the separately owned 15-container canonical UI
stack. This closes the bounded ownership-observability investigation but does not replace the
still-required daily, recovery, poison, duplicate, correction, restatement, and pre-merge proof.

Exact clean daily `20260717T201508Z` at signed `4525d56cb` made all `100,000` source
transactions durable but reached `87,671` completed transaction operations and `87,550` snapshots
before the fixed two-hour drain deadline. Attempts remained `2/2`, repeats and governed service
errors remained zero, and failed outbox remained zero. The bounded twelve-to-fourteen transaction
capacity experiment that followed did not close this gap: two exact fan-ins reconciled but drained
in `100.732s` and `105.721s`, with portfolio-day aggregation completion facts increasing to `2`
and then `9`. Signed `ca730d5da` reverted the experiment forward. The governed transaction
capacity ceiling remains twelve.

The next retained slice used the position-state row lock already acquired by successful generation
rearm to pass the current epoch to cashflow inside the same unit of work. Exact clean fan-in
`20260717T231632Z` at signed `a8d6ee302` reconciled all `1,000` rows with attempts `2/2`, zero
repeats/errors/open jobs/outbox failures, `3/3` peak lock waiters/blocked sessions, and `100.608s`
drain. `PositionStateRepository.get_or_create_state` fell from the prior two-call pattern to exactly
`1,000` observations for `1,000` completed transactions (`17.876655s` accumulated). The direct
two-to-one lookup reduction justifies retaining the simpler ownership shape, but the drain and two
aggregation completions do not prove end-to-end throughput improvement or justify another daily
run. JSON SHA-256 is
`E0D89A92A58E3C15C26ADD3234313AD32E45E8E9444B215318D88D9A57824999`.

A bounded follow-up tested whether moving the existing synchronous, post-processing Kafka offset
commit off the asyncio event loop improved cross-partition throughput without changing commit
semantics. Exact clean fan-in `20260717T234511Z` at signed experiment head `704358fe0`
reconciled all `1,000` rows, retained attempts `2/2`, zero repeats/errors/DLQ/outbox residue, and
one aggregation completion, but drained in `100.783s` versus `100.608s` at parent `a8d6ee302`.
That `0.17%` regression is effectively neutral and does not justify the executor path. Signed
`e79496822` reverted the experiment forward. Do not repeat synchronous-commit executor offload
without a workload that directly proves commit latency is the limiting factor. JSON SHA-256 is
`D73EADB166CCC9591E8AA1E15CB1B20E75E43AEF794604EFF3E24AAF76673B34`.

Cleanup-fenced exact daily `20260718T002619Z` at clean signed head `45fe19d1e` is a valid
certifying capacity failure, not an external-kill diagnostic. All `100,000` source transactions
became durable in `126.893s`, but the fixed deadline ended after `7,564.478s` with `89,163`
completed transaction operations, `89,012` valuation snapshots, `87,878` position time-series
rows, and `957` portfolio time-series rows. This improves completed snapshots by `1,462` (`1.67%`)
over valid daily `20260717T201508Z`, confirming the retained lock-scoped epoch reuse helped without
closing the remaining capacity gap. Valuation attempts remained exactly `2/2`, repeated processing
and governed error lines remained zero, failed outbox remained zero, and all run-owned containers,
networks, and volumes were removed while the separate canonical UI project remained untouched.

The report recorded `57` peak database connections, `21` active connections, `28`
idle-in-transaction connections, and `7/7` lock waiters/blocked sessions. It also exposes one
bounded same-pattern amplification: the runtime loaded the effective cashflow-rule snapshot only
`25` times but executed `89,138` `get_rule_set_version` queries, totalling `1,730.304179s` across
concurrent observations at a `0.019411521s` mean. These cumulative durations are attribution, not
wall-clock savings. Any retained fix must preserve governed rule-update visibility through a
bounded freshness contract, explicit invalidation, missing-rule refresh, and concurrency proof;
it must pass exact fan-in before another daily certification run. JSON and Markdown SHA-256 values
are respectively `CD19ACE2555FC85385697E1D2A574D75A7367E99CDEE6473F089D52CEF523DB6` and
`8A6FF684110135E34189C7FE24A963DCEA7DB626490E627556607CF2F2914DEB`.

The bounded five-second cashflow rule source-version interval at signed experiment head
`31ac198a4` reduced exact fan-in version queries from `999` to `19`, but two consecutive clean runs
drained in `110.821s` and `110.768s` versus the retained `100.608s` parent. Both runs reconciled
exactly with attempts `2/2`, zero repeats/errors, one aggregation, and outbox `0/0`; the repeat also
reduced database pressure to `46/7/16` peak total/active/idle-in-transaction connections and `1/1`
lock waiters/blocked sessions. The consistent `10.15%` and `10.10%` end-to-end regressions outweigh
the `98.10%` query-count reduction, so the experiment was reverted forward. Do not repeat it without
new workload evidence proving end-to-end improvement. Exact hashes and the compatibility decision
are retained in CR-1631.

Exact-main Main Releasability run `29639937110` then exposed two correctness gaps that ordinary
unit proof had not closed. A transient `cost_dependency_unavailable` failure on one
`transactions.persisted` record advanced the consumer fetch position without an in-session retry,
so its second dual-leg record never reached readiness within the existing 240-second budget. The
same run's four analytics timeseries nodes observed a later FEE position mutation after the cash
valuation job had already completed; transaction readiness did not rearm that completed job, so the
freshness join correctly excluded the stale cash row.

Signed commits `2f34dcd1c` and `92d4eedea` added ordered in-process retry plus phase-specific DLQ and
post-DLQ-commit recovery. The previously failing dual-leg node then passed without raising its
timeout. Signed commits `d7ae37da2`, `4c0289900`, and `c79bf0afe` made transaction readiness rearm
from the durable outbox mutation identity while preserving the event payload and headerless
compatibility. Exact-head E2E at `c79bf0afe` passed all four affected timeseries contract nodes in
`155.53s`; an immediately preceding same-runtime run at `2fb5ecb09` also passed `4/4` in `113.72s`.
Both used isolated dynamic-port Compose projects, retained the original test budgets, removed every
run-owned resource, and preserved the separately owned 15-container canonical Core stack.

Exact-main Main Releasability run `31264609366` timed out the full burst profile after `180s` on
both the original attempt and exact-SHA failed-job rerun. All services remained healthy and the
failure showed no database, Kafka, or DLQ growth. Review found the supposedly deterministic
profile embedded its wall-clock run id in the Kafka partition keys, randomized transaction ids,
and restarted one shared transaction timestamp/sequence between phases. The result changed the
twelve-lane key distribution on every run and made the burst phase retroactive relative to steady
state. Replay `409` responses were also counted as accepted work that could never complete.

The corrected full profile
`output/task-runs/20260808T174445Z-performance-load-gate.json` passed with exact processing and no
DLQ growth: steady state drained `200` records in `32.513s` against the `60s` SLO; burst drained
`640` records in `63.730s` at `9.958 records/s` against the unchanged `180s` SLO; and the replay
storm drained `480` accepted records in `117.804s` against the unchanged `180s` SLO. Compared with
the last append-incorrect local burst at `205.921s`, deterministic append ordering reduced measured
burst drain by `69.05%`. This is focused load-gate recovery evidence; it does not replace #795's
daily, restart, poison, duplicate/concurrency, correction, and restatement acceptance matrix.

## Compatibility

HTTP APIs, OpenAPI schemas, Kafka topics, event payload schemas, transaction calculations,
idempotency identities, outbox atomicity, and database schemas are unchanged.

With a positive retry budget, the shared consumer retries a failed record in the same process and
preserves per-partition order until it succeeds or reaches governed terminal recovery. With the
default disabled budget, it stops after one attempt without committing so restart/rebalance can
redeliver the failed offset; it cannot process or commit a later offset on that partition first.
Existing retry settings, DLQ topics, payloads, commit-after-confirmation rule, and consumer groups
are unchanged. The new execution-profile backoff field is additive and defaults to one second.

Transaction readiness reuses the existing dispatcher-owned `outbox_id` header; it does not add an
event field or require a schema-version transition. A distinct durable outbox mutation can rearm or
fence valuation work, while the same outbox redelivery and headerless compatibility records remain
non-disruptive. No migration, public API, or downstream payload change is required.

The bootstrap sequencing change affects only the canonical local seed workflow and the internal
no-horizon source schedule. It adds no API, OpenAPI, event, migration, database, calculation,
partition, readiness, or downstream contract. Existing-horizon backdated and future corrections
retain their durable replay behavior.

The workload JSON config changes additively with `source_revision` and `source_tree_state`; neither
field contains file names, command output, credentials, or runtime configuration. Their presence
does not elevate local workload evidence to CI or production certification.

Transaction-processing operation evidence is also additive to the generated JSON/Markdown artifact
and runner configuration. It reuses existing bounded metrics and changes no service instrumentation,
runtime behavior, API, event, calculation, or persistent schema. Stage/outcome labels contain no
portfolio, security, account, or transaction identifiers. The internal cost evidence has the same
compatibility posture and uses only bounded mode and cost-basis-method labels.

Database operation evidence is likewise additive and reuses the existing low-cardinality
repository/method histogram. It records no query text, SQL values, or business identifiers and
changes no production instrumentation, transaction boundary, lock, API, event, schema, or
calculation contract.

The lock-scoped epoch handoff is internal application-port metadata. It does not extend the row
lock or unit-of-work lifetime, and it preserves the existing stale/current/future epoch comparison.
Cashflow falls back to the database fence unless a conditional position-state update proves both
the expected epoch and the row lock are still owned by the current unit of work. No external API,
event, persistence, calculation, or error contract changes.

The intentional transport behavior change is the transaction partition key:
`portfolio_id` becomes `portfolio_id|security_id` for unlinked raw ingestion, persisted transaction
facts, and repair replay. Linked multi-leg transactions instead use
`portfolio_id|transaction-group|linked_transaction_group_id` across all three paths, preventing a
canonical parent-before-dependent-leg sequence from landing on different partitions. Existing
deployed topics require the governed pause/drain/cutover procedure because historical and new keys
can map to different partitions after producer rollout.

The P1 review fix changes only Kafka record keys for transactions carrying a non-blank existing
`linked_transaction_group_id`. HTTP APIs, OpenAPI, event payload schemas, database schemas, and
migrations are unchanged. The event-contract pack, RFC-0082, repository context, operator runbook,
review ledger, and campaign manifest record the new truth. No wiki source changes because the wiki
does not publish this key policy; the operator-owned migration runbook is the durable runbook owner.

## Validation

- `10` outbox repository unit tests and `13` PostgreSQL outbox-dispatcher integration tests passed.
- `105` focused hot-path logging tests passed across persistence, transaction economics, valuation,
  derived state, and the durable guard.
- `51` transaction partitioning/replay/ingestion/persistence tests passed, including real ingestion
  API paths.
- The linked-group P1 fix passed `47` focused partitioning, ingestion, persistence, and repair-replay
  tests; full repository-native MyPy passed all `235` source files; scoped Ruff lint and format
  checks passed. Signed implementation commit: `dcb1aba71d47ab5d72732921a802135276a21143`.
- Event runtime contract, event contract test pack, structured-log, domain, application workflow,
  infrastructure adapter, event publisher, repository port, wiki, and documentation guards passed.
- Full `make typecheck` passed for `235` source files.
- Rebuilt diagnostic smoke `20260716T175518Z` completed with exact `10/10` transaction-to-timeseries
  evidence, attempt count `2/2`, zero repeats, and closed queues.
- Rebuilt certifying fan-in `20260716T183314Z` passed with the measured result above.
- Cashflow and position-history PostgreSQL lifecycle, duplicate, repair, backdated, and concurrency
  tests passed before their commits.
- Residual logging validation passed `76` focused tests, the structured-log and complete
  architecture guards, full MyPy across `235` files, Ruff/format, and exact fan-in
  `20260717T000106Z`.
- Coalesced progress-read validation passed `19` unit tests, `5` PostgreSQL
  repository/lifecycle/concurrency scenarios, full MyPy and architecture guards, Ruff/format, and
  exact fan-in `20260717T001431Z`.
- Twelve-way transaction capacity passed `167` focused provisioning, consumer, supportability, and
  runtime-contract tests; event runtime/contract-pack guards, full MyPy, Ruff/format, complete
  architecture guards, and exact fan-in `20260717T003225Z` passed.
- Cost-reference coalescing passed `105` focused unit tests, `74` transaction-processing contract
  tests, `2` real PostgreSQL integration tests including a one-statement guard, full MyPy across
  `235` source files, Ruff/format, and complete architecture guards. Remote Feature Lane
  `29578198110` passed at signed commit `2d49fc8f1`.
- Exact fan-in `20260717T115854Z` completed with exact `1,000` reconciliation, attempts `2/2`, zero
  repeats/open jobs/outbox failures, and `120.492s` drain. Parent diagnostic
  `20260717T121025Z` completed equivalently with `125.478s` drain.
- Source-provenance runner tests passed `14` cases with touched Ruff/format and diff checks at signed
  commit `70ae16f0f`; exact-head Remote Feature Lane `29579810885` passed.
- Position-state creation passed `11` database-unit tests, `29` focused position tests, and the
  `75`-test PostgreSQL transaction-processing contract; Remote Feature Lane `29591744921` passed at
  signed commit `a3c9eeaac`.
- Initial-opening-lot persistence passed `22` focused application tests, `72` cost-processing unit
  tests, `2` targeted PostgreSQL statement/lifecycle tests, and the full `75`-test PostgreSQL
  transaction-processing contract. MyPy across `235` files, Ruff/format/diff, the architecture
  guard, and Remote Feature Lane `29593836128` passed at signed commit `b7e7e1be2`.
- Transaction-operation evidence collection and managed dynamic-endpoint fix-forward passed `41`
  focused runner/parser/orchestration tests, full MyPy across `235` source files, Ruff/format/diff,
  the complete architecture and wiki/documentation guards, synthetic-fixture leakage, and
  repository output-shape validation. Exact fan-in `20260717T162223Z` passed, and Remote Feature
  Lane `29595818757` passed at signed head `20333978a`.
- Internal cost-evidence parsing and fail-closed report behavior passed `44` focused
  runner/parser/orchestration tests plus scoped MyPy, Ruff/format, and diff checks before commit.
- Terminal valuation/snapshot inconsistency detection passed `19` focused bank-day tests plus
  scoped MyPy, Ruff/format, and diff checks at signed commit `6640ec911`. Remote Feature Lane
  `29597316430` passed at the exact cost-evidence head `37abbf19b`; Remote Feature Lane
  `29599992446` then passed at the exact fail-fast head `6640ec911`.
- Exact clean fan-in `20260717T174251Z` passed at `d34da9305` with the measured result above;
  Remote Feature Lane `29600977253` passed at that exact source head. Scoped teardown removed every
  run-owned resource while retaining the separately owned canonical UI stack.
- Database-operation parsing, incomplete-series exclusion, fail-closed collection, report
  propagation, and config proof passed `32` focused tests plus scoped MyPy, Ruff, format, and diff
  checks at signed commit `37ffa2fad`. Remote Feature Lane `29602493876` passed at that exact head.
- Exact clean fan-in `20260717T180631Z` failed fast with the measured ownership contradiction and
  retained eleven bounded database series. Managed teardown removed all run-owned containers,
  networks, and volumes while preserving the 15-container canonical UI stack.
- Terminal-transition classification passed the full unit lane (`4,878` passed, `11` deselected),
  `41` affected valuation unit tests, `5` isolated real-PostgreSQL ownership/lifecycle tests,
  focused MyPy, Ruff/format/diff checks, and the complete architecture guard at signed commit
  `45295cf24`.
- Exact clean fan-in runs `20260717T193156Z` and `20260717T194013Z` both passed at `45295cf24` with
  exact reconciliation, attempts `2/2`, zero repeats, closed jobs/outbox, no governed error lines,
  and zero `REQUEUED` or `NOT_OWNED` suppression warnings. The repeat restored the intended single
  aggregation completion and `95.645s` drain. Both scoped teardowns preserved canonical UI.
- Lock-scoped epoch reuse passed `873` transaction-processing/common unit tests, `2` real-
  PostgreSQL atomic reprocessing tests, full MyPy across `235` source files, Ruff/format, complete
  architecture, and documentation/wiki guards at signed commit `a8d6ee302`.
- PR #804 review found that the lock-scoped epoch had been read before the watermark `UPDATE`; a
  concurrent worker could advance the row before that update acquired its lock. The rearm now
  applies an expected-epoch compare-and-set predicate. Focused position, cashflow, transaction, and
  shared-repository tests cover stale-epoch rejection and the database-fence fallback contract.
- Exact clean fan-in `20260717T231632Z` passed at `a8d6ee302` with the direct one-state-read-per-
  transaction result above. Scoped teardown removed every run-owned resource and preserved the
  separately owned 15-container canonical UI stack.
- Synchronous Kafka commit executor-offload validation passed the full unit lane (`4,886` passed,
  `11` deselected), `68` focused Kafka-consumer tests including same-partition ordering and
  cross-partition commit concurrency, full MyPy across `235` source files, the duplicate-delivery
  concurrency guard, Ruff/format, complete architecture, and documentation/wiki guards at signed
  experiment head `704358fe0`.
- Exact clean fan-in `20260717T234511Z` passed at `704358fe0` but was neutral at `100.783s` drain
  versus `100.608s` at its parent. Signed `e79496822` reverted the unproven executor complexity
  forward; scoped teardown preserved the cleanup fence and all 15 canonical UI containers.
- Cleanup-fenced exact daily `20260718T002619Z` failed validly at clean signed head `45fe19d1e`
  after making all `100,000` source transactions durable and reaching `89,012` snapshots before
  the fixed deadline. Attempts stayed `2/2`, repeats/errors/failed outbox stayed zero, and scoped
  teardown removed all run-owned resources. The governed background task
  `eng-task-20260718-082223-lotus-core-derived-state-daily` reconciled to `FAILED` with exit code
  `2`; dependent recovery, poison, duplicate, and restatement gates remain withheld.
- The bounded source-version interval passed focused and broad static/unit validation at signed
  `31ac198a4`, but exact fan-in `20260718T030244Z` and repeat `20260718T031229Z` regressed drain to
  `110.821s` and `110.768s` versus `100.608s` while reducing version queries from `999` to `19`.
  The implementation was reverted forward; CR-1631 preserves the hashes and no-repeat decision.
- PR Merge Gate run `29628815481` exposed an asynchronous certification-harness race: the runtime
  surface smoke published a transaction and immediately requested replay before the persistence
  consumer had made the source-owned transaction row durable. The replay API correctly returned
  `404`, while the other `65` runtime surface checks passed. Signed `997d99908` now waits for the
  exact transaction identifier in the query ledger before issuing the one-shot replay command.
  It does not retry the side-effecting POST or weaken the required `202` response. All `9` focused
  smoke-script tests, scoped Ruff lint/format, and diff checks passed.
- PR #804 review identified that price and FX correction fan-out could pass 10,000 valuation jobs
  into one PostgreSQL multi-VALUES statement and exceed the driver's bind-parameter ceiling. The
  same-pattern scan found the shared repository also owned configurable backfill callers and an
  unbounded tuple-scope lookup. The repository boundary now preserves full-call normalization and
  deterministic lock order while executing both statement families in ordered chunks of at most
  1,000 rows. High-fanout unit proof covers the 1,001-row boundary for both paths; focused and broad
  validation is recorded on PR #804 and issue #799.
- Shared consumer retry/DLQ recovery passed `114` focused consumer/configuration tests before the
  first two signed commits. The final affected package run passed `245` tests; full MyPy passed all
  `235` source files; event-runtime, event-contract, structured-log, and duplicate-delivery guards
  passed.
- PR #807 review found that the ordered DLQ recovery loops treated the default disabled failure
  budget (`0`) as unlimited retries. A sustained DLQ publication or post-publication commit outage
  could therefore pin the consumer instead of preserving restart redelivery. Signed fix-forward
  commit `7c71a77b0` stops after the first failed recovery phase when the budget is disabled, leaves
  the source offset uncommitted, and emits bounded `dlq_recovery_stopped` evidence. Positive values
  remain the only way to enable bounded in-process recovery. Both recovery phases have direct
  regressions; the focused shared-consumer suite passes `73/73` and full MyPy passes all `237`
  source files.
- A later PR #807 review found the primary ordered-processing loop had the same default-disabled
  inversion: because neither zero budget could exhaust, a persistent retryable failure slept and
  retried forever. Signed fix-forward commit `2f9ba4611` restores the compatibility path before the
  sleep: one attempt, no DLQ or commit, and an explicit
  `kafka_redelivery_after_restart_or_rebalance` disposition. Positive attempt or elapsed budgets
  remain the only opt-in to ordered in-process retry. The focused shared-consumer and PM-book
  regression run passed `79` tests; scoped Ruff and full MyPy across `237` sources passed.
- A subsequent PR #807 review proved that returning from the failed message was still insufficient:
  the serial loop could poll a later record and the concurrent finalizer could resume or schedule a
  queued same-partition record, allowing its successful commit to skip the failed offset. Signed
  fix-forward commit `fee372a72` now stops the consumer on the first unbudgeted retryable failure,
  discards queued records for the failed partition, and emits bounded
  `redelivery_required/retryable_consumer_restart_required` evidence. Direct serial and concurrent
  regressions prove the later offset is neither processed nor committed; `95` Kafka-library tests,
  strict MyPy across `237` sources, and the event-runtime ownership guard pass.
- Exact-main dual-leg reproduction failed before the shared retry fix and passed afterward without
  increasing its 240-second budget. Exact-head timeseries contract E2E passed `4/4` at signed
  `c79bf0afe` in `155.53s` with dynamic ports and project-scoped teardown.
- Canonical branch-qualified run `20260719T042919Z` proved the prior DNS/port conflict resolved and
  then timed out after `900s` with all source facts durable but no valuation readiness: source-first
  ordering was absent, producing `6,567` completed reset watermarks, `6,101` completed FX reset
  watermarks, and repeated portfolio aggregation while historical sources drained. The bounded fix
  makes no-horizon source observations non-replaying and fences both price and FX query visibility
  before calendar activation. Focused source-scheduling/consumer/seed proof passed `81` tests and
  the wider valuation-orchestrator package passed `163` tests with warnings treated as errors before
  final validation.
- The retained-volume canonical rerun at exact signed head `f5aa531e0` drained both twelve-partition
  market-price groups to zero and then converged valuation and aggregation queues to zero without a
  deadlock, stale lease, failed job, PANIC, OOM, or exit-137 signature. It exposed a separate
  app-local composition defect: all `376` reconciliation requests were durably published, but
  Compose launched only `uvicorn app.main:app`, so the required consumer group did not exist and
  holdings correctly remained `UNRECONCILED`/`UNKNOWN`.
- The bounded fix restores the Dockerfile-owned `python -m app.runtime` entry point, explicit
  `kafka:9093` configuration, and topic-creator dependency. Ten focused stack/runtime tests and
  `docker compose config --quiet` passed. A targeted one-service recreation then started the
  reconciliation consumer and outbox dispatcher, created
  `portfolio_day.reconciliation.requested_group`, drained partition 3 from offset `0` to `376`, and
  produced completed reconciliation runs without service errors. Exact verify-only initially
  remained fail-closed because mixed source-row epochs did not match the one latest-portfolio-epoch
  control. Signed fix `a3d8dee29859f5ddd3749590039642b81e17fda8` then made those rows one
  collective portfolio-day scope and selected every authoritative security row at or below the
  target epoch. Fresh correlation `CTL:a3d8dee:PB_SG_GLOBAL_BAL_001:2026-04-10:3` completed all
  three controls; position valuation examined 11 mixed-epoch securities with zero findings and both
  completion outbox events processed with zero retries. Full canonical queue convergence and the
  remaining #795 load/recovery/correction profiles are still required.
- Exact-main canonical validation later exposed eight terminal transaction semantic conflicts even
  though the 31 canonical transactions were durable and all derived-state queues drained. The eight
  DLQ records were the three missing BUYs plus their cash legs and a dividend plus its cash leg.
  PostgreSQL retained 45 `portfolio-transaction-processing` physical fences from other demo
  portfolios, including reused `transactions.persisted-{partition}-{offset}` identities, because
  the destructive local reseed reset that topic family but omitted the unified transaction consumer
  from its volatile service fence set. The bounded correction adds only that service to the existing
  topic/service cleanup cross-product; the same-pattern scan confirmed the other physical-offset
  consumers are either already covered (`position-valuation-calculator`) or intentionally outside
  the canonical seed's reset topic family (`financial-reconciliation-requested`).
- A fresh governed rerun after the physical-fence correction accepted all `31` canonical
  transactions and materialized `11` positions, all `11` with valuations. Position and cash data
  quality both reached `COMPLETE`; analytics, performance, and return evidence reached
  `2026-04-10`; advisor-book governed membership and source evidence remained current; and every
  valuation and aggregation pending/processing/stale/failed count reached zero. The pre-existing
  eight DLQ records did not increase. This is live acceptance for the reseed-fence slice, not the
  remaining daily/recovery/poison/duplicate/correction/restatement acceptance of #795.
- Exact-main daily certification task
  `eng-task-20260809-192100-lotus-core-certification-make-profile-derived-state-daily` built the
  exact source and completed isolated migration/startup, but produced no bank-day artifact and
  exited before workload evidence. A bounded live diagnostic exposed the source-contract drift:
  the bank-day generator still emitted date-only `transaction_date` values after ingestion began
  enforcing governed timezone-aware transaction instants. The correction preserves the business
  date separately and emits its start-of-day UTC instant. Same-pattern scanning found the other
  operational transaction producers already emit aware UTC values. Reused-stack diagnostic
  `20260809T114049Z` then passed with exact `10` transactions/jobs/snapshots/position rows, two
  portfolio rows, exact quantity and market-value reconciliation, attempts `2/2`, zero repeats,
  closed valuation/aggregation queues, and no failures. This proves the generator correction only;
  it does not substitute for the 100,000-transaction certifying profile.
- The first exact-source failure also exposed an evidence-lifecycle gap: managed Compose startup or
  migration could exit before the bank-day child created its normal report. Workload, interruption-
  recovery, and poison gates now share one atomic, credential-redacting
  `lotus.managed-gate-orchestration-failure.v1` receipt. It records phase and owned Compose/log
  context, re-raises the original error, and is always `non_certifying_failure`; it cannot satisfy
  load, recovery, or poison acceptance.
- #794's report contract now carries monotonic recent publication-age p50/p95/p99 plus an observed
  processed-event throughput window. The percentile query is deliberately bounded to the newest
  10,000 primary-key rows rather than sorting the full amplified outbox on every sample. Live SQL
  returned `0.208127s / 0.77536835s / 1.08417709s`; `EXPLAIN (ANALYZE, BUFFERS)` used a backward
  `outbox_events_pkey` scan, limited exactly 10,000 rows, and completed in `63.624ms` without a new
  index or migration. Exact pending/retry/failed totals and topic cohorts remain full-table evidence.
- #794 now owns one machine-readable `docs/standards/outbox-capacity-profile.v1.json` capacity
  profile for development, CI, and the two consolidated production runtimes. It binds the candidate
  `1s/1000` cadence with the complete claim, shutdown, and retry settings.
  `make outbox-capacity-profile-guard` cross-checks Kafka delivery and runtime supervision constants
  and rejects deployment drift. The profile remains
  `candidate_pending_exact_source` until the final current-source daily receipt passes.
- `make test-outbox-capacity-acceptance` now executes the same contract's deduplicated direct
  PostgreSQL nodes before its allow-listed managed restart target. It accepts only exact test-node
  references and single Make targets, passes argv directly without a shell, and stops on the first
  failed phase. The JSON remains the only failure-mode list; no parallel test manifest was added.
- Capacity evidence now retains low-cardinality producer aggregate-type/topic cohorts from the
  existing topic query and fails closed when cohort, topic, and final status totals diverge. Live
  `EXPLAIN (ANALYZE, BUFFERS)` completed the extended query in `187.430ms` versus `218.392ms` for
  the prior topic-only query on the active amplified table; both used the same parallel sequential
  scan and tiny 24–26kB aggregates, so no index or migration was added.
- The detached old-source daily diagnostic at `314f9d8ae` reached 64,517 measured transaction
  completions with `0.927174s` mean transaction time and `0.350548s` mean cost-stage time, while
  pure FIFO recalculation remained only `0.001121s` mean at depth one. Existing repository metrics
  attributed repeated position/state/lock/rule operations but left most cost persistence opaque.
  Signed commit `b8e26d927` adds bounded static repository/method timings for that persistence path
  and makes the certifier fail closed unless eight representative cost series are present. It does
  not change statements, locking, calculations, or runtime concurrency; the next exact-source run
  must use the new series to justify any persistence change.
- The same-pattern queue scan found ingestion's operator health projection aggregating completed
  reprocessing history even though its contract reports only pending, processing, and failed
  pressure. The bounded query excludes completed-only history before grouping, retains every
  observable state, and documents that zero-pressure historical job types are absent rather than
  forcing the database to revisit their terminal rows.
- Corrected-source daily task
  `eng-task-20260809-215800-lotus-core-certification-make-profile-derived-state-daily` failed before
  ingestion at clean signed `de0145b3c`: SQLAlchemy adapted the one-element Python date collection
  as a tuple, which PostgreSQL rejected as a `date[]` literal. Receipt
  `20260809T140708Z-bank-day-load.json` is therefore non-certifying harness evidence (SHA-256
  `D79159645F5C0B02543AE966A0C521CA668B7D7F3B55E647EBAC669CB5F34AE5`), not a capacity verdict.
  The horizon fence now transports its bounded date set as JSON and expands it inside PostgreSQL,
  avoiding driver-specific array adaptation for both one and multiple dates. Focused unit tests and
  a live PostgreSQL two-date binding probe passed; no production query, schema, or runtime contract
  changed.
- The first corrected-harness exact-source daily at signed `3f770ce09` is a valid internal capacity
  failure, not an orchestration diagnostic. Task
  `eng-task-20260809-221942-lotus-core-certification-make-profile-derived-state-daily` accepted all
  100,000 transactions through the public API in `126.70s`, then exhausted the unchanged two-hour
  end-to-end drain with 82,802 snapshots, 82,785 position-series rows, 904 portfolio-series rows,
  30 open valuation jobs, nine open aggregation jobs, maximum valuation attempt four, and 3,941
  repeatedly processed jobs. Artifact `20260809T142151Z-bank-day-load.json` has SHA-256
  `F63514EDFB8E89E67EF463B59EA57E839EE8064ED13DD224E7ED22276D77805B`.
  Outbox publication remained bounded (164 peak pending, zero failed, `78.900264/s` observed
  processed throughput), so the failure does not justify more dispatcher capacity. The new operation
  evidence instead attributes mean `0.889971171s` transaction time to `0.336456535s` cost and
  `0.178394358s` position stages while FIFO calculation itself remained `0.001073069s` at depth one.
  Required cost persistence calls each observed roughly 24.6–59.0ms fixed database latency. The
  next slice must reduce proven transaction-scoped round trips while preserving ordering, locks,
  atomicity, calculations, event contracts, the 12-partition ceiling, and the rejected-experiment
  exclusions.
- Position persistence accounted for `0.178394358s` mean stage time in that exact-source artifact;
  the sum of its measured repository calls was `0.177557555s`, or 99.53% of the stage. The ordinary
  current-stream path read the prior position anchor and affected booked transactions in two
  sequential post-lock queries. One domain-owned `PositionReplayWindow` now loads both from the
  same post-lock database snapshot with deterministic transaction-date/transaction-id ordering.
  The initial-stream statement shape therefore removes one fixed-latency query (measured prior
  anchor call `0.025202879s`, projecting about 14.1% from the position stage) without moving the
  lock, changing the delete boundary, weakening the epoch-fenced rearm, or altering calculations,
  lineage, events, schema, or public contracts. Focused unit proof passed 26 tests; live PostgreSQL
  replay-window proof passed two tests with exactly one SELECT; same-key serialization and rollback
  atomicity proof passed four tests.
- A cost-stream experiment that acquired the advisory lock and read its replay checkpoint inside
  one SQL statement was rejected and fully reverted before commit. Under PostgreSQL READ COMMITTED,
  a statement snapshot can precede an advisory-lock wait, so a caller unblocked by a committing
  predecessor could read a stale checkpoint from the waiting statement's older snapshot. Future
  cost round-trip work must keep lock acquisition and freshness-dependent reads in separate
  statements or prove an equivalent fresh-snapshot boundary; a lower statement count is never a
  substitute for deterministic replay authority.
- Canonical transaction economics update and stale fee-breakdown deletion were two sequential
  executes even though both mutations already shared one caller-owned transaction. One PostgreSQL
  data-modifying CTE now makes the fee deletion depend on the successful canonical-row update,
  returns the updated row without rereading it, and leaves replacement fee inserts staged for the
  same unit-of-work flush. A missing canonical row therefore cannot delete fee evidence. The
  ordinary initial-BUY cost shape falls from 11 to 10 database statements, removing one call from
  a repository operation that measured `0.058990828s` mean in the exact-source daily failure.
  Thirty-four focused repository tests, live PostgreSQL fee replacement/rollback proof, and the
  exact initial-BUY statement-count test passed. Calculations, lineage, fee identity, lock order,
  replay behavior, schema, events, and public contracts are unchanged.
- Exact clean fan-in task
  `eng-task-20260810-005849-lotus-core-certification-make-profile-derived-state-fan-in` at signed
  head `0d4990036` completed and reconciled all 1,000 transactions, snapshots, position-series rows,
  and the portfolio-series row with zero open jobs, DLQ events, log errors, or financial findings.
  Artifact `20260809T170050Z-bank-day-load.json` has SHA-256
  `80EA208206FBD3F8A00F904A0548EA90725855FD02E63A5670B51D8FEB8DE3A1`. It remains a valid
  correctness failure: 21 valuation jobs were processed twice, maximum valuation attempt count was
  four, 1,001 snapshot events were emitted for 1,000 snapshots, and three aggregation completion
  cohorts were published. Drain was `161.436s`, including an `84.110312s` position-to-portfolio
  tail. The new combined position replay-window query measured `0.019874997s`; the two superseded
  post-lock reads were absent, proving the preceding round-trip reduction without claiming an
  end-to-end pass.
- The failure exposed the same stale-source-event race in price and direct-pair FX correction
  selection. Both queries treated an absent snapshot as unconditional correction authority. A
  source fact committed before a newly materialized position was therefore scheduled again if its
  Kafka event arrived after position readiness, even though readiness necessarily valued from that
  already-committed fact. Both selectors now compare source `updated_at` with the latest available
  derived authority: the snapshot when present, otherwise the current position-history row. A
  source older than the position is left to ordinary readiness; a genuinely later correction still
  schedules revaluation. Six live PostgreSQL cases cover long/short positions, source-before-
  position convergence, source-after-position correction, snapshot freshness, and a subsequent
  correction; 36 valuation scheduling/requeue unit tests also pass.
- Exact clean fan-in task
  `eng-task-20260810-012200-lotus-core-certification-make-profile-derived-state-fan-in` at signed
  head `2c68a905f` proved that freshness correction was beneficial but incomplete. Artifact
  `20260809T172908Z-bank-day-load.json` has SHA-256
  `D11CD9B6A8BD5369F4D9565FD82ED94B80260374DF0C1CEB179473AE95248964`. It reconciled all
  1,000 transactions and derived rows with zero open jobs, failed outbox rows, DLQ events, log
  errors, or financial findings. Drain fell from `161.436s` to `85.804s`, the
  position-to-portfolio tail fell from `84.110312s` to `2.366197s`, and aggregation completion
  cohorts fell from three to two. It still correctly failed: 40 valuation jobs reached attempt four
  and 1,001 snapshot events were emitted. Daily certification remains withheld. The workload
  receipt now retains at most 25 synthetic repeated-job samples with source-correction and
  correlation lineage so the next exact run can identify the winning trigger without retaining an
  unbounded high-cardinality dump or relying on timing inference.
- Exact clean fan-in task
  `eng-task-20260810-014321-lotus-core-certification-make-profile-derived-state-fan-in` at signed
  head `f4ab7ecfc` reconciled all 1,000 transactions, snapshots, position-series rows, and the
  portfolio-series row in `90.653s`, but correctly failed certification: 30 valuation jobs were
  repeated, maximum attempt count reached four, and 1,007 snapshot events were published. Artifact
  `20260809T175045Z-bank-day-load.json` has SHA-256
  `D54AA9E97A3EFC6AEED5DB8B1E36D9088B071713113983AF0AA933EC490C8943`. Every sampled repeat
  carried scheduler-backfill correlation without source-correction lineage, while the latest
  position-history rows predated the affected jobs. The remaining race was delayed delivery of a
  readiness outbox event whose committed position mutation had already been covered by a valuation
  claim.
- Valuation claims now snapshot the maximum committed readiness outbox ID for the exact
  portfolio/security/date/epoch scope. The readiness consumer rearms or requeues only for a
  positive delivered outbox ID newer than that durable watermark. Truly headerless legacy
  deliveries remain non-rearming compatibility inputs; a present malformed or nonpositive header
  fails closed before idempotency is claimed. Transport input never initializes the claimed
  watermark. Exact JSON payload identity supplements the
  aggregate ID, preventing delimiter collisions, and the watermark is monotonic when outbox history
  is later pruned. Eleven live PostgreSQL cases cover delayed replay, later mutation, uncommitted
  exclusion, other-date isolation, completed-job idempotency, retention, non-ISO `DateStyle`,
  aggregate-ID collision, rollback sequence gaps, unverified high transport input, and
  deterministically contended same-position publication through the production lock adapter.
- Exact clean fan-in task
  `eng-task-20260810-022442-lotus-core-certification-make-profile-derived-state-fan-in` at signed
  head `1db5ee8d2` completed with exact 1,000-row reconciliation, attempts `2/2`, zero repeated
  valuation jobs, exactly 1,000 snapshot events, pending/failed outbox `0/0`, and `95.773s` drain.
  Artifact `20260809T183144Z-bank-day-load.json` has SHA-256
  `B3A40B16E16434F27E8BC2EDD7D3CE78BF7079FAD6531F797390B643181C3F83`. It remains diagnostic,
  not certifying: exact-head review found that malformed-present headers downgraded to legacy
  behavior and that transport input could initialize the monotonic watermark. The artifact also
  records two aggregation-completion revisions for the one portfolio day; distinct revisions are
  valid continuous-processing evidence, but this superseded run does not carry enough lineage to
  classify their trigger. Corrected-head fan-in remains mandatory.
- The transaction-readiness lookup now has a live PostgreSQL query-plan regression at 10,000
  unrelated outbox rows. It requires `ix_outbox_events_aggregate_id` in the executed plan and
  rejects a sequential scan, while retaining exact-scope payload verification after the indexed
  candidate lookup. Twenty-five focused PostgreSQL integration tests, two helper unit tests, and
  scoped Ruff, format, MyPy, and diff checks passed at signed commit `3d6e3aed7`.
- Transaction readiness previously used four serial database calls on the ordinary successful
  path: advisory-lock acquisition, latest-epoch read, stage upsert, and completion claim. Signed
  commit `640603322` keeps lock acquisition as its own statement so a waiter receives a fresh
  PostgreSQL READ COMMITTED snapshot, then performs the existing-stage capture, monotonic upsert,
  and exact-epoch completion claim in one data-modifying statement. The path is now two database
  calls without weakening same-owner collision handling, stale-epoch suppression, duplicate
  completion behavior, rollback atomicity, or durable outbox authority. Eleven focused unit/live
  PostgreSQL tests and the 122-test transaction-processing contract passed.
- Exact clean fan-in task
  `eng-task-20260810-055424-lotus-core-certification-make-profile-derived-state-fan-in` at signed
  head `640603322` completed with exact 1,000 transaction, snapshot, position-series, and
  portfolio-series reconciliation; attempts `2/2`; zero repeated processing; zero open valuation
  or aggregation jobs; and final pending/failed outbox `0/0`. Artifact
  `20260809T215625Z-bank-day-load.json` has SHA-256
  `621D0C1BA13F2B69224F431679610FE03991BE042C2C5C96F2522273C106C51C`. Drain fell from the
  accepted corrected-head `115.998s` to `80.982s`, a 30.19% reduction. Mean readiness-pipeline
  duration fell from about `0.0958s` to `0.035358507s` (63.09%), and mean total transaction
  processing fell from about `0.8757s` to `0.644479942s` (26.41%). Exact project-scoped teardown
  left zero owned containers, networks, or volumes and did not touch the healthy shared stack.
  This passes the retain gate and authorizes one exact-head daily capacity rerun.
- The authorized clean daily task
  `eng-task-20260810-081125-lotus-core-certification-make-profile-derived-state-daily` at
  `640603322` made all 100,000 source transactions durable but reached 89,742 valuation snapshots,
  89,737 position-series rows, and 991 portfolio-series rows before the fixed drain deadline.
  Attempts remained `2/2`, repeated processing remained zero, failed outbox remained zero, terminal
  timestamps were advancing, and exact project-scoped teardown completed. This is valid remaining
  transaction-capacity evidence, not an external-kill or harness verdict. Artifact
  `20260810T001245Z-bank-day-load.json` has SHA-256
  `DC33C7DE1E25E8A9EA38F86D26D111C11F7A93DF311BFF2DE246A19E8C92BD03`.
- That daily artifact also exposed a measurement defect: its final outbox status total and
  independently queried topic cohorts observed different READ COMMITTED instants while dispatch
  was still advancing. Signed `d7504da92` loads exact totals, bounded recent-age evidence, and
  topic cohorts in one SQL statement and one statement snapshot. The report contract and field
  names are unchanged. Twenty-seven focused tests, the capacity guard, scoped static checks, and a
  real PostgreSQL integration proof passed.
- Signed `c207fc87f` introduces a typed post-lock cost-basis calculation context. After the existing
  portfolio/security advisory lock, one statement loads the durable checkpoint and loads ordered
  initial history only when no checkpoint exists. The ordinary first-position path falls from ten
  PostgreSQL statements to nine; checkpoint-backed paths do not hydrate history. Lock order,
  READ COMMITTED freshness, deterministic ordering, calculations, replay, and unit-of-work
  atomicity are unchanged. Thirty-four focused unit tests and real PostgreSQL same-key concurrency
  and query-shape proofs passed. Exact clean fan-in remains the retain gate before another daily
  run.
- Exact-head fan-in task
  `eng-task-20260810-104948-lotus-core-certification-make-profile-derived-state-fan-in` completed
  exact reconciliation at `c207fc87f` with attempts `2/2`, zero repeats, closed jobs/outbox, and no
  governed log errors, but correctly failed its evidence guard because the required-operation list
  still named the two replaced repository methods. Artifact
  `20260810T025158Z-bank-day-load.json` has SHA-256
  `4D152015C4EEA6863A9AB5A61CB2B586DEC77E4C03E039358DDFE3D8D032978D`. The combined context read
  averaged `0.045831484s`, versus `0.049195006s` for the former checkpoint plus history reads in
  retained parent fan-in `20260809T215625Z`, a direct 6.84% reduction. End-to-end drain was
  `95.809s` versus `80.982s`; all major database stages were slower on that run, so no end-to-end
  improvement is claimed. The required-operation contract now names the combined context method
  and has an explicit regression test. A clean corrected-head fan-in rerun remains mandatory.
- Corrected-head fan-in task
  `eng-task-20260810-105813-lotus-core-certification-make-profile-derived-state-fan-in` passed at
  clean exact SHA `d3a911171` with exact 1,000 transaction, snapshot, position-series, and one
  portfolio-series reconciliation; valuation attempts `2/2`; zero repeated processing; closed
  valuation, aggregation, and outbox queues; complete required database-operation evidence; and no
  governed log errors. Artifact `20260810T025932Z-bank-day-load.json` has SHA-256
  `32152255C76AF4A5AA1C536F1520EE9A5EF18DD4F4EAA3D37347902CE4BFFA26`. Drain was `95.872s`,
  effectively identical to the corrected-but-evidence-incomplete `95.809s` run. It remains slower
  than the unusually fast `80.982s` parent while all major database stages were slower, so only
  correctness, evidence completeness, and the direct combined-read reduction are claimed. Exact
  project-scoped cleanup completed and this retain gate authorizes one clean exact-head daily run.
- The authorized daily task
  `eng-task-20260810-110402-lotus-core-certification-make-profile-derived-state-daily` was stopped
  before certification after same-pattern review found that the combined context join no longer
  trimmed persisted transaction portfolio, security, and excluded transaction identifiers. This
  would have regressed CR-475 for padded historical rows even though the synthetic fan-in data was
  normalized. Only the exact owned process tree and Compose project
  `lotus-integration-derived-state-daily-workload-44fb3627` were stopped; verified remaining owned
  processes, containers, networks, and volumes were all zero. The interrupted attempt is not
  capacity evidence.
- Signed `0859fb0c1` restores trim-normalized persisted history matching and exclusion inside the
  combined statement. The unit query-shape proof requires all three `trim(...)` predicates, and a
  live PostgreSQL test persists deliberately padded historical rows, retrieves the prior row from
  normalized caller IDs, and excludes the padded in-flight transaction. Four focused unit tests,
  scoped Ruff/format/MyPy, and the live PostgreSQL proof passed. Public contracts, stored source
  values, case semantics, lock order, calculations, and database schema remain unchanged. A clean
  exact-head fan-in and daily run are required again.
- Exact-head fan-in task
  `eng-task-20260810-111503-lotus-core-certification-make-profile-derived-state-fan-in` passed at
  clean signed SHA `178f51764` with exact 1,000 transaction, snapshot, position-series, and one
  portfolio-series reconciliation; attempts `2/2`; zero repeated processing; closed jobs/outbox;
  zero governed log errors; and `85.748s` drain. Artifact
  `20260810T031659Z-bank-day-load.json` has SHA-256
  `21CEBD54D30A2858D2231EAF723B5228E4767590DFDA5D3B9F99BC34176FB31C`. The combined context read
  averaged `41.819565ms`, but drain remained 5.89% slower than the retained `80.982s` parent.
- Exact-head daily task
  `eng-task-20260810-112042-lotus-core-certification-make-profile-derived-state-daily` then reached
  a valid capacity failure at the same clean signed SHA. All 100,000 transactions were durable, but
  only 81,957 snapshots, 81,938 position-series rows, and 907 portfolio-series rows completed by
  the fixed deadline. Attempts stayed `2/2`, repeated processing and governed log errors stayed
  zero, failed outbox stayed zero, and terminal timestamps were still advancing. Peak database
  total/active/idle-in-transaction connections were `63/30/32`, with `5/5` lock waiters/blocked
  sessions. Exact scoped teardown left zero owned containers, networks, and volumes. Artifact
  `20260810T032203Z-bank-day-load.json` has SHA-256
  `FA1CC560B9768028B9CF6C2533D1AC4D509AD49A4BE3637B6A21914AAEC30F9B`; its Markdown receipt has
  SHA-256 `552570ACA1B2968045857EB074EE645DC583C74C391E0E13F90CEC2ADBC3223D`.
- The daily result is 7,785 fewer snapshots (`-8.67%`) than retained exact daily
  `20260810T001245Z`, while average whole-transaction duration rose from `805.132ms` to
  `885.184ms`. Three exact fan-ins at or after the combined context change were also slower than
  the parent. Although the combined read itself reduced direct query time, it did not improve the
  end-to-end workload and added a new port, repository, join, mapping surface, and evidence name.
  Signed `4775aef83` and `33874e340` therefore revert the normalization follow-up and combined
  context experiment forward. The established trim-normalized history repository contract remains
  authoritative, and certifying evidence again requires the separate checkpoint and history
  operations. Do not repeat the combined context experiment without new end-to-end evidence.
- Signed `9babe76fa` introduces a dedicated initial-opening cost-state application port and one
  PostgreSQL statement that persists the ordinary first BUY's opening lot, accrued-income offset,
  and deterministic processing checkpoint as data-modifying CTEs. The existing lot, offset, and
  checkpoint statement builders remain the single payload and conflict-policy truth. Corrections,
  replay suffixes, disposals, transfers, AVCO, calculation lineage, lock order, and unit-of-work
  rollback retain their specialized paths. This removes two database round trips from the dominant
  daily transaction path without changing economics or external contracts. The slice passed 249
  focused unit tests, four live PostgreSQL/end-to-end replay-update/rollback/BUY-SELL proofs,
  strict MyPy, repository-pinned Ruff, and the complete architecture guard.
- Exact-head fan-in task
  `eng-task-20260810-140612-lotus-core-certification-make-profile-derived-state-fan-in` at clean
  signed `9babe76fa` reconciled exactly with attempts `2/2`, zero repeats, closed jobs/outbox, and
  zero governed errors, but drained in `136.278s`. Cost-stage aggregate time fell from `294.247s`
  to `221.240s` and whole-transaction time fell from `725.861s` to `595.510s`; the new aggregate
  write averaged `34.255ms` versus `55.980ms` for the former instrumented lot-plus-checkpoint
  writes. The total drain outlier was isolated to `63.057s` position-to-portfolio aggregation
  latency and lower downstream outbox throughput. Artifact `20260810T060812Z-bank-day-load.json`
  has SHA-256 `5D4ED65591CFD402CA817E706B4DDBB68FB469F984443C93B692C7C4EEA13085`.
- Same-code repeat fan-in task
  `eng-task-20260810-141344-lotus-core-certification-make-profile-derived-state-fan-in` at clean
  signed formatting head `28a475c9d` passed exact reconciliation with attempts `2/2`, zero
  repeats, closed jobs/outbox, zero governed errors, and `80.866s` drain. This is 11.11% faster
  than the restored-path `90.979s` run and 0.14% faster than the retained `80.982s` best. Cost
  stage remained 16.09% lower than the restored path; the aggregate write averaged `37.434ms`, at
  least 33.13% below the former two instrumented writes, while the removed accrued-offset write
  had not been timed. Position-to-portfolio latency returned to `0.972s`, confirming the first
  run's downstream outlier. Artifact `20260810T061507Z-bank-day-load.json` has SHA-256
  `6A5285C17DADEBFB2FFDCBCCDA1E9FD7C402BBA5FB93A5FA7FFA11BAFA3AB1F2`; exact scoped cleanup is
  `DONE`. The repeat retain gate authorizes one exact-head daily run.
- Exact-source daily task
  `eng-task-20260810-182408-lotus-core-certification-make-profile-derived-state-daily` at clean
  signed `3c46b699f` reached its governed two-hour deadline and wrote complete evidence. All 100,000
  transactions were durable, but only 74,805 snapshots and 807 of 1,000 portfolio aggregates were
  complete. Attempts remained `2/2`, repeated valuation jobs and failed outbox rows remained zero,
  while 13 valuation jobs, 16 aggregation jobs, and 18 pending outbox rows remained. Peak database
  total/active/idle-in-transaction connections were `63/22/33`; lock waiters/blocked sessions were
  `4/4`. Artifact `20260810T102534Z-bank-day-load.json` has SHA-256
  `082C6C9FDDC8A086F128FEAECD33E69056F3D12C8A202A6F88588BB30F79C760`. This is a valid capacity
  failure, not an infrastructure-kill or correctness verdict, and it withholds the downstream
  recovery, poison, correction, and restatement gates.
- Signed `86923a58e` then combined the already post-lock current-epoch suffix delete and replay-window
  load into one data-modifying CTE. The bounded slice passed 21 focused unit tests and six live
  PostgreSQL query-shape, rollback, atomicity, same-key serialization, and different-key
  concurrency tests. Candidate fan-in `20260810T132520Z` reconciled exactly in `146.083s` but
  included a `55.045s` aggregation-tail outlier; SHA-256
  `18FFA70174D751E08A0A27E845B9FE990E7D9BDD211AC26775DDEDDB016B03A7`.
- Same-code repeat `20260810T133059Z` reconciled exactly with attempts `2/2`, zero repeats, final
  outbox `0/0`, zero governed errors, normal `1.406s` aggregation tail, and `95.906s` drain; its
  SHA-256 is `7B8530A723EEFC2D5115E5C635EA8B62D62E69A8EE7199B6EF4CB4729EAE3D88`. The combined statement
  averaged `0.032928s`, but drain regressed `18.60%` and whole-transaction mean regressed `34.12%`
  against retained parent `20260810T061507Z` (`80.866s`, `0.595510s`). The micro-optimization
  therefore failed the end-to-end retain gate. Signed `79457e0e4` reverts it forward; do not repeat
  post-lock delete/load coalescing without fresh workload evidence identifying it as material.
- Signed `3cea6a8bd` then combined the ordinary first-BUY canonical transaction-economics update and
  fee replacement with the retained opening-lot, accrued-income-offset, and checkpoint aggregate.
  The bounded slice passed 38 focused tests, the 125-test transaction-processing contract, strict
  MyPy, Ruff, the architecture guard, and live PostgreSQL idempotency, update, rollback, and
  concurrency proofs. Direct live evidence reduced the dominant path from eight statements to
  seven without changing its unit-of-work boundary.
- Exact clean candidate fan-in `20260810T141804Z` reconciled all 1,000 transactions, snapshots,
  position rows, and the portfolio row with attempts `2/2`, zero repeats, final outbox `0/0`, and
  zero governed errors, but drained in `100.688s` and averaged `0.821858004s` per whole
  transaction. Artifact SHA-256 is
  `4E46BFEBE13C1F7346B7642F862274E533FD9AE1A78C403B936CF08E35B4C75F`.
- Same-code repeat `20260810T142323Z` also reconciled exactly with attempts `2/2`, zero repeats,
  final outbox `0/0`, and zero governed errors, but drained in `110.953s` and averaged
  `0.903795135s` per whole transaction. Artifact SHA-256 is
  `B794E1C5188940532C35A2CF5933A0D2F4D0EECF8FC74A15110A85ACAE06E260`. Against retained parent
  `20260810T061507Z` (`80.866s`, `0.595510s`), the two candidates regressed drain by `24.51%` and
  `37.21%` and whole-transaction mean by `38.01%` and `51.77%`. Signed `615e27772` reverts the
  experiment forward; its tree is identical to retained documentation head `3c245adbb`. Do not
  repeat transaction-economics/fee aggregation without fresh end-to-end evidence identifying it
  as material.
- PR #931 is capped as a coherent delivery tranche at signed evidence head `c220b33de`, 73 commits
  ahead of its governed base. It retains only improvements that passed their scoped correctness and
  performance gates and retains forward reverts plus no-repeat evidence for the two rejected final
  experiments. The valid daily capacity failure remains authoritative; recovery, poison,
  correction, restatement, qualified-release, and downstream proof stay pending. Delivery of this
  tranche therefore closes no campaign issue and grants no fixed-local status. The unchanged
  acceptance matrix transfers to the next branch after exact-main validation and wiki publication.

Implementation commits include `23fc6faf3`, `d51adb739`, `ad1ad179d`, `57f8c60e2`,
`4f05be9a5`, `c230d660a`, `f42f6eaa3`, `d56e14dbf`, `2d49fc8f1`, `70ae16f0f`,
`a3c9eeaac`, `b7e7e1be2`, `35fb5d84f`, `20333978a`, `37abbf19b`, `6640ec911`, `37ffa2fad`, and
`45295cf24`, `a8d6ee302`, `704358fe0`, `e79496822`, `2f34dcd1c`, `92d4eedea`,
`d7ae37da2`, `4c0289900`, `2fb5ecb09`, and `c79bf0afe`. Evidence alignment continues through
`c79bf0afe`; #794 capacity governance continues through `39b9aac48` and `29e63a1eb`; human
contract/context alignment starts in `9d6dbbbf9`.

## Documentation Decision

Repository context, event contracts, ingestion guidance, the endpoint certification audit, and the
partition migration runbook changed because transport ordering truth changed. The workload
provenance contract also changes operations guidance and authored `wiki/` source; publish and verify
wiki parity after merge. No public OpenAPI change is required. The cashflow, position unit-of-work,
residual logging, and cost-reference slices change no public or operator workflow beyond the
recorded workload evidence fields. The position-state and initial-opening-lot statement reductions
also require no additional OpenAPI, migration, event-contract, operator-runbook, or wiki source
change. Operation-evidence collection changes the bank-day runbook and authored wiki source because
operators gain a new required certifying diagnostic; publish and verify wiki parity after merge.
The terminal valuation/snapshot invariant also changes operator-facing failure diagnosis, so the
bank-day runbook and authored wiki record the fail-fast condition in this slice. It does not require
an OpenAPI, migration, event-contract, or calculation-methodology change. Database-operation
attribution extends the same generated artifact and runbook contract; it adds no new production
metric and requires no OpenAPI, migration, event-contract, calculation-methodology, or additional
wiki-source change. The terminal-transition outcome classification changes only an internal Python
repository/processor contract and diagnostic log fields. It requires no OpenAPI, migration,
event-contract, calculation-methodology, operator-runbook, or additional wiki-source change.
The lock-scoped position epoch handoff and its expected-epoch compare-and-set hardening are internal
unit-of-work behavior. They require no OpenAPI, migration, event-contract, calculation-methodology,
operator-runbook, or additional wiki-source change.
The rejected synchronous-commit executor experiment changed no durable contract and was reverted
forward. Recording its no-repeat evidence requires no OpenAPI, migration, event-contract,
calculation-methodology, operator-runbook, or wiki-source change.
The exact daily failure adds evidence only. It requires no OpenAPI, migration, event-contract,
calculation-methodology, operator-runbook, or additional wiki-source change.
The post-lock position replay-window consolidation changes one internal repository port and query
shape only. It preserves lock order, delete and replay boundaries, deterministic transaction order,
epoch fencing, calculations, lineage, APIs, OpenAPI, events, database schema, runtime settings, and
operator commands. This review record is the durable evidence; no migration, runbook, repository
context, calculation-methodology, or authored wiki change is required.
The atomic transaction-economics/fee-replacement statement changes only internal PostgreSQL query
shape inside the existing unit of work. It preserves fail-closed missing-row behavior, rollback,
fee components, calculation lineage, APIs, OpenAPI, events, database schema, locks, runtime settings,
and operator commands. No migration, runbook, repository context, calculation-methodology, or
authored wiki change is required.
The price/FX correction freshness fix changes only internal source-correction selection. It
preserves the readiness and persisted-source event schemas, source values, valuation calculations,
lineage, requeue fencing, APIs, OpenAPI, database schema, partitioning, runtime settings, and
operator commands. This review record and executable tests are the durable truth; no migration,
runbook, repository context, calculation-methodology, or authored wiki change is required.
The rejected source-version interval and its operator setting were reverted forward. The canonical
immediate source-version validation contract is restored; retaining the experiment evidence requires
no OpenAPI, migration, event-contract, calculation-methodology, operator-runbook, or wiki-source
change.
The runtime-smoke readiness fix changes only certification sequencing. It preserves the replay API,
HTTP status contract, source-owned transaction resolution, runtime topology, and production
behavior, and requires no OpenAPI, migration, event-contract, operator-runbook, or wiki-source
change.
The valuation-job statement bound is an internal persistence safeguard. It preserves transaction
atomicity, normalization, deterministic lock order, rearm/requeue semantics, public contracts, and
runtime configuration. It requires no OpenAPI, migration, event-contract, calculation-methodology,
operator-runbook, or wiki-source change.
The consumer recovery and transaction-readiness convergence fixes change internal delivery and
job-scheduling behavior only. The readiness event payload/schema, topics, public OpenAPI, database
schema, calculations, and operator commands remain unchanged. Repository context and this review
record change because the durable source-mutation and same-session retry rules are reusable
engineering truth. No migration or authored wiki change is required.
The PR review fix clarifies the existing DLQ failure-budget runbook and repository context because
default-zero and positive-budget behavior are operator-facing recovery truth. It changes no command,
environment-variable name, API, event, database, calculation, or authored wiki contract.
The final primary-loop correction makes the restart/rebalance requirement operationally explicit in
the existing runbook, repository context, and Operations wiki. It changes no command,
environment-variable name, OpenAPI, event, migration, database, or calculation-methodology
contract; no new standalone document is required.
The canonical bootstrap correction changes the existing seed contract, repository context, and
Operations wiki because source-first ordering and bounded readiness fences are operator truth. It
requires no OpenAPI, migration, event-contract, calculation-methodology, partition, or additional
standalone documentation change.
The financial-reconciliation Compose correction restores the already documented service ownership
and runtime topology. Repository context and the review ledger change because worker-entrypoint
parity is reusable engineering guidance. No OpenAPI, migration, event, calculation, operator
command, or authored wiki truth changes; the existing wiki already states that financial
reconciliation consumes portfolio-day requests, so this slice records an explicit no-wiki-change
decision.
The canonical reseed physical-fence correction changes only destructive app-local certification
cleanup. It preserves production consumer idempotency, semantic-conflict protection, APIs, events,
topics, partitions, database schema, calculations, and operator commands. Repository context,
executable cleanup tests, this review record, and #795 own the reusable rule; no OpenAPI, migration,
runbook, or authored wiki change is required.
The deterministic performance-profile correction changes only certification identities, ordering,
one read of existing fixture history, accepted-work accounting, and timeout diagnostics. It does
not change production Kafka keys,
topics, partition counts, consumer concurrency, APIs, event schemas, database schemas, calculations,
or runtime settings. The existing load command is unchanged, and this review/context update is
sufficient durable guidance; no OpenAPI, migration, operator-runbook, or authored wiki change is
required.
The bank-day temporal-input correction changes only repository-owned workload payload generation.
It aligns `transaction_date` with the already-governed ingestion/event contract while preserving
the separate business/trade date, transaction identities, workload volume, ordering keys, APIs,
OpenAPI, events, database schemas, calculations, Kafka configuration, and production runtime. The
existing command and operator procedure are unchanged; repository context and this review own the
repeatable rule, so no migration, runbook, or authored wiki change is required.
The cost-persistence timing extension changes only bounded internal metrics and certifying evidence
completeness. Its labels are fixed repository/method names without business identifiers, and it
changes no API, OpenAPI, event, database statement/schema, calculation, lock, partition, runtime
setting, operator command, or authored wiki truth.
The readiness-sequence fence adds one non-null, default-zero internal valuation-job database column
through migration `c150b2c3d517`. It changes no public API, OpenAPI field, Kafka topic, event payload,
partition key, calculation, or downstream consumer contract. Truly headerless readiness records
remain consumable but cannot fabricate rearm authority; malformed-present headers fail closed.
Only exact-scope database evidence observed by a claim advances the monotonic watermark. Repository context,
this review, the existing runtime contract, and authored Timeseries and Aggregation wiki are updated
in place; no new standalone document is required.
Exact-head review changed no API, schema, Kafka payload, or operator command. It tightened only the
consumer boundary and claimed-authority source, replaced a timing-dependent lock test with an
explicit failed try-lock followed by the production lock adapter, and requires one corrected-head
profile rerun. No additional wiki or OpenAPI change is required.
The readiness lookup plan guard and atomic readiness claim change only an internal indexed query,
repository port, and transaction-processing persistence statement. They preserve the separate
advisory-lock freshness boundary, event payloads, outbox authority, public APIs/OpenAPI, database
schema, calculations, partition policy, runtime settings, and operator commands. This review and
executable PostgreSQL tests are the durable truth; no migration, event-contract, runbook,
calculation-methodology, or additional authored-wiki change is required.
The atomic outbox evidence read changes only internal certification query shape and preserves the
existing generated report contract, bounded age window, exact totals, operator command, and
capacity threshold. The typed cost-basis calculation context changes only an internal application
port and post-lock query shape. It preserves public APIs/OpenAPI, events, database schema,
calculation and ordering rules, locks, runtime settings, and operator commands. This review and the
existing bank-day runbook are sufficient durable truth; neither slice requires a migration,
event-contract, calculation-methodology, repository-context, or additional authored-wiki change.
The cost-history normalization correction restores the established CR-475 repository-boundary
contract for historical padded identifiers. It changes no API/OpenAPI, event, schema, migration,
calculation, stored source value, case semantic, operator command, repository context, or authored
wiki truth; this review and the existing CR-475 record are sufficient durable documentation.
The combined cost-context experiment and its normalization follow-up are reverted forward after
repeat fan-in and exact daily evidence failed the retain gate. The restored separate checkpoint and
trim-normalized history reads preserve the pre-experiment API/OpenAPI, event, schema, migration,
calculation, lock, ordering, runtime-setting, and operator contracts. The certifying operation guard
is restored in the same slice; no additional runbook, repository-context, or authored-wiki change
is required beyond this durable rejected-experiment evidence.
The atomic initial-opening cost-state statement changes only internal PostgreSQL query shape and
application-port composition inside the existing transaction-processing unit of work. It preserves
calculation economics and lineage, deterministic ordering, lock scope, rollback, APIs/OpenAPI,
events, database schema, migrations, runtime settings, and operator commands. The existing
bank-day evidence artifact now requires the aggregate operation instead of the two superseded
individual operations. This review, executable guards, and workload artifacts are sufficient
durable truth; no additional repository context, methodology, runbook, or authored-wiki change is
required.
The rejected position reset/replay-window coalescing experiment changed only an internal
post-lock PostgreSQL query shape and was reverted forward after repeated fan-in evidence failed the
end-to-end retain gate. The restored separate delete and replay-window ports preserve lock order,
deterministic replay, correction/backdated semantics, calculations and lineage, APIs/OpenAPI,
events, database schema, partitions, runtime settings, and operator commands. This review and the
issue evidence are the durable no-repeat record; no migration, repository-context, runbook,
methodology, or authored-wiki change is required.
The rejected transaction-economics/fee aggregation experiment changed only an internal first-BUY
PostgreSQL query shape and was reverted forward after two exact fan-ins failed the end-to-end
retain gate. The restored persistence calls preserve transaction economics, fee replacement,
lineage, missing-row failure, opening-state atomicity, rollback, APIs/OpenAPI, events, database
schema, partitions, runtime settings, and operator commands. This review and the issue evidence are
the durable no-repeat record; no migration, repository-context, runbook, methodology, or
authored-wiki change is required.
## Service-attributed database evidence addendum (2026-08-11)

Issue #502's attribution-first slice adds a fixed Core runtime inventory and publishes its stable
`SERVICE_NAME` through PostgreSQL `application_name` for shared sync/async engines, Alembic, the
bank-day monitor, Compose, and the two deployed Kubernetes runtimes. The identity is shared by
replicas and never derived from pod, host, PID, worker, request, transaction, portfolio, account, or
security identity. Production-like engines fail before construction when identity is missing or
invalid. Local/test fallbacks remain available for developer and test execution but fail a
certifying profile if observed. The recurring PostgreSQL health probe has its own fixed identity so
sampling alignment cannot create a false unattributed-session failure.

The existing database-resource statement now returns bounded per-application connection, active,
idle-in-transaction, open-transaction, lock-waiter, blocked-session, and oldest-transaction-age
cohorts. It remains one statement at the existing cadence. Every sample reconciles cohort totals to
the aggregate total/active/idle counts, and certifying evidence rejects missing reconciliation,
unattributed sessions, ungoverned identities, and local/test identity. Retained reports
contain only bounded peaks, never PIDs, SQL text, transaction IDs, raw samples, or business keys.
The existing Prometheus pool labels are unchanged.

Focused local proof passes 77 unit/deployment tests and five real-PostgreSQL tests covering psycopg,
asyncpg, concurrent named sessions, exact reconciliation, and redaction of ungoverned identity,
plus scoped Ruff and focused MyPy.
The slice uses mature PostgreSQL connection metadata and existing SQLAlchemy/Prometheus runtime
capabilities; it adds no dependency, agent, sidecar, datastore, image, deployable, topology, pool,
timeout, recycle, concurrency, or partition change. API/OpenAPI, events, schemas, migrations,
calculations, ordering, and downstream contracts are unchanged. Repository context, operations
guidance, and the existing Timeseries and Aggregation wiki are updated in place; no new standalone
document or central Platform skill/context change is needed. Issues #502 and #795 remain open until
non-regressing fan-in and exact daily evidence support a further capacity decision. Technology
governance and vulnerability-release gaps remain explicitly owned by #720, #926, #927, and #928.

The PR #931 tranche boundary changes only delivery packaging and campaign chronology. It does not
change runtime behavior or any API/OpenAPI, event, schema, migration, calculation, partition,
operator, repository-context, or authored-wiki contract. Existing authored wiki changes already
owned by the PR remain subject to post-merge publication and strict parity verification.
