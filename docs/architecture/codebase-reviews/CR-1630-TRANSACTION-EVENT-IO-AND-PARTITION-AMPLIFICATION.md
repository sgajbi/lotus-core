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
4. Transaction ingestion, raw persistence outbox, and repair replay all use the same normalized
   `portfolio_id|security_id` key.
5. Dates and epochs remain outside the key, preserving one position stream across normal,
   duplicate, backdated, reversal, correction, restatement, and corporate-action processing.
6. Cross-security corporate-action and linked-leg correctness remains explicit through dependency
   references, deterministic domain ordering/rebuild, reconciliation, and portfolio-security
   database locks rather than portfolio-wide Kafka serialization.
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

## Compatibility

HTTP APIs, OpenAPI schemas, Kafka topics, event payload schemas, transaction calculations,
idempotency identities, outbox atomicity, and database schemas are unchanged.

The workload JSON config changes additively with `source_revision` and `source_tree_state`; neither
field contains file names, command output, credentials, or runtime configuration. Their presence
does not elevate local workload evidence to CI or production certification.

Transaction-processing operation evidence is also additive to the generated JSON/Markdown artifact
and runner configuration. It reuses existing bounded metrics and changes no service instrumentation,
runtime behavior, API, event, calculation, or persistent schema. Stage/outcome labels contain no
portfolio, security, account, or transaction identifiers.

The intentional transport behavior change is the transaction partition key:
`portfolio_id` becomes `portfolio_id|security_id` for raw ingestion, persisted transaction facts,
and repair replay. Existing deployed topics require the governed pause/drain/cutover procedure
because historical and new keys can map to different partitions after producer rollout.

## Validation

- `10` outbox repository unit tests and `13` PostgreSQL outbox-dispatcher integration tests passed.
- `105` focused hot-path logging tests passed across persistence, transaction economics, valuation,
  derived state, and the durable guard.
- `51` transaction partitioning/replay/ingestion/persistence tests passed, including real ingestion
  API paths.
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

Implementation commits include `23fc6faf3`, `d51adb739`, `ad1ad179d`, `57f8c60e2`,
`4f05be9a5`, `c230d660a`, `f42f6eaa3`, `d56e14dbf`, `2d49fc8f1`, `70ae16f0f`,
`a3c9eeaac`, `b7e7e1be2`, `35fb5d84f`, and `20333978a`. Human contract/context alignment starts in
`9d6dbbbf9`.

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
