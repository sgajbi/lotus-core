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
    session. Retryable failures use the governed attempt/elapsed budget and bounded backoff. Terminal
    recovery separately retries DLQ publication and the post-DLQ commit without rerunning business
    processing or republishing an already confirmed DLQ record.
18. Transaction valuation readiness treats each durable outbox event as a distinct source mutation.
    The consumer hashes the existing `outbox_id` Kafka header to rearm a completed natural-key job or
    request requeue when a different mutation arrives during processing. Same-outbox redelivery is
    non-disruptive; headerless compatibility records keep the prior non-rearming behavior. The
    readiness payload, schema version, topic, partition key, and consumer group remain unchanged.

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

## Compatibility

HTTP APIs, OpenAPI schemas, Kafka topics, event payload schemas, transaction calculations,
idempotency identities, outbox atomicity, and database schemas are unchanged.

The shared consumer now retries a failed record in the same process and preserves per-partition
order until it succeeds or reaches governed terminal recovery. Existing retry budgets, DLQ topics,
payloads, commit-after-confirmation rule, and consumer groups are unchanged. The new execution
profile backoff field is additive and defaults to one second.

Transaction readiness reuses the existing dispatcher-owned `outbox_id` header; it does not add an
event field or require a schema-version transition. A distinct durable outbox mutation can rearm or
fence valuation work, while the same outbox redelivery and headerless compatibility records remain
non-disruptive. No migration, public API, or downstream payload change is required.

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
- Exact-main dual-leg reproduction failed before the shared retry fix and passed afterward without
  increasing its 240-second budget. Exact-head timeseries contract E2E passed `4/4` at signed
  `c79bf0afe` in `155.53s` with dynamic ports and project-scoped teardown.

Implementation commits include `23fc6faf3`, `d51adb739`, `ad1ad179d`, `57f8c60e2`,
`4f05be9a5`, `c230d660a`, `f42f6eaa3`, `d56e14dbf`, `2d49fc8f1`, `70ae16f0f`,
`a3c9eeaac`, `b7e7e1be2`, `35fb5d84f`, `20333978a`, `37abbf19b`, `6640ec911`, `37ffa2fad`, and
`45295cf24`, `a8d6ee302`, `704358fe0`, `e79496822`, `2f34dcd1c`, `92d4eedea`,
`d7ae37da2`, `4c0289900`, `2fb5ecb09`, and `c79bf0afe`. Evidence alignment continues through
`c79bf0afe`; human
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
