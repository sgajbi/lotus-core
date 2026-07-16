# Current Source Revaluation Amplification

## Objective

Remove redundant valuation replay created by current-business-date price and FX observations while
preserving effective-dated correction behavior.

## Finding

The exact-source 100,000-transaction daily profile accepted the complete input workload but failed
to drain within the fixed two-hour budget. At timeout, Core had created `135,982`
`valuation.snapshot.persisted` outbox events for `94,933` unique daily snapshots. PostgreSQL
reached `98.33%` runtime CPU, seven blocked sessions, and a position-timeseries p95 handoff latency
of `1,583.10s`.

The initial price and FX facts were current for the governed business date and arrived before any
positions existed. Both source handlers nevertheless staged durable replay. As positions became
visible, that replay reset already-correct position epochs and repeated valuation and derived-state
work. This was unnecessary because transaction processing already emits one valuation-readiness
fact for every later position mutation, and valuation reads the committed current price and FX
facts.

The next exact-source run proved a second amplification path after source replay was removed.
Scheduler backfill used a different correlation id from transaction readiness, and the valuation
job upsert treated that lineage difference as permission to reopen an already `COMPLETE` job. At
diagnostic interruption, Core had accepted `16,671` transactions but emitted `14,025` valuation
snapshot events for only `9,804` snapshots; `4,204` valuation jobs had been processed twice.
Correlation identity describes operational lineage and cannot authorize replay or state mutation.

## Implemented Direction

1. `source_revaluation.py` owns one framework-neutral temporal scheduling policy for price and FX
   observations.
2. A current-date observation scans currently visible positions for immediate valuation but does
   not stage durable replay.
3. A current-date observation with no visible positions relies on the later transaction-owned
   valuation-readiness fact.
4. Backdated observations retain immediate visible-position jobs plus durable replay.
5. Future observations and observations received before a business-date horizon retain durable
   replay and defer the visible-position scan.
6. FX plans expose whether replay was actually staged rather than defaulting the evidence to true.
7. Immediate price and FX selection compares the persisted source row's `updated_at` with the
   same-day snapshot. Missing or older snapshots are queued; snapshots materialized after the
   source fact suppress delayed duplicate notifications; a later source correction becomes
   eligible again.
8. Price and FX correction writers opt into a single-row in-flight supersession fence. When a
   different source correction meets a `PROCESSING` natural-key valuation job, the row retains its
   active status and records one durable requeue request. FX uses the persisted observation ID;
   price uses a deterministic hash of canonical persisted business content. Transport correlation
   remains diagnostic and is not correction identity. The active owner atomically returns the row
   to `PENDING` and reports that it did not complete, preventing publication of the stale snapshot.
   Same-source and ordinary readiness duplicates remain non-disruptive. Stale-claim and dispatch
   recovery consume the same fence without dropping a correction at the retry limit.
9. Completed valuation jobs remain idempotent across different scheduler, readiness, and recovery
   correlation ids. Only price and FX correction handlers can request explicit completed-job
   rearming, after source-versus-snapshot freshness proves that newer authoritative input exists.
10. Raw transaction persistence resolves portfolio, instrument, and optional effective cash-account
   availability in one repository query before upsert. This removes one database round trip from
   every normal transaction while preserving portfolio retry, provisional instrument/cash
   reference policy, idempotency, outbox, and event contracts.

## Compatibility

Public APIs, persisted source-event schemas, Kafka topics, and position valuation formulas are
unchanged. Migration `c114b2c3d4f3` adds two internal job columns: one non-null, false-defaulted
queue fence and one nullable source-correction identity. This keeps accepted source revisions
distinct from transport tracing. The intentional internal behavior change removes redundant
current-date replay while preserving a newer correction that races with active valuation work.
Backdated and future correction contracts remain unchanged.

## Validation

- `104` valuation-orchestrator and valuation-job repository unit tests passed.
- `3` focused PostgreSQL price/FX freshness lifecycle tests passed.
- Review fix-forward proof passed `72` focused unit checks and `2` isolated PostgreSQL queue
  lifecycle scenarios: same-source delivery remains a no-op, while a different correction
  stays fenced during `PROCESSING`, causes the stale owner to return false, and becomes `PENDING`
  under the newer source correction identity even when transport correlation is shared.
- Focused Ruff lint and format checks passed.
- Full repository `make typecheck` passed for `235` source files.
- Architecture boundary, domain layer, application workflow policy, and infrastructure adapter
  guards passed.
- Full `make coverage-gate` passed: `4,840` unit tests and the `51`-test valuation PostgreSQL
  package were green; changed critical files measured `95.15%` line and `88.77%` branch coverage,
  with migration `c114b2c3d4f3` at `100%` line coverage and the valuation job repository at
  `93.52%` line / `92.31%` branch coverage.
- Rebuilt diagnostic smoke `20260716T130810Z` passed with `10` transactions, snapshots, completed
  valuation jobs, and snapshot events; valuation attempt count min/max were both `2`, repeated-job
  count was `0`, queues and outbox closed, blocked sessions were `0`, and peak derived-state CPU
  was `4.66%`.
- Exact run `20260716T131058Z` proved amplification removal but missed the two-hour drain deadline:
  `98,759` transactions were durable; `95,693` completed valuation jobs all had attempt count `2`;
  repeated-job count was `0`; failed outbox and DLQ counts were `0`. The remaining tail was
  transaction persistence/processing and position-timeseries throughput, not duplicate valuation.
- Post-throughput-fix rebuilt smoke `20260716T152953Z` passed the same exact `10/10` job/event and
  attempt-count assertions, with zero blocked sessions and closed queues.

The implementation source commits are `4b8a4c772`, `fd7c71fa5`, `e5083a4ff`, `4709b0b53`, and
`7ba71a04e`;
the signed in-flight correction fix-forward is `a0ae66c88`. The prior failed certifying artifact is
`output/task-runs/20260716T095705Z-bank-day-load.json`. An initial local lifecycle attempt reused a
prebuilt migration image at Alembic head `c113b2c3d4f2` and failed because the `c114b2c3d4f3`
column was absent; it is invalid harness evidence, not a behavior verdict. The branch-local
migration image and governed `unit-db` rerun passed. Other diagnostic artifacts are
`output/task-runs/20260716T123231Z-bank-day-load.json` and
`output/task-runs/20260716T131058Z-bank-day-load.json`. Fresh runtime evidence remains required
before issue `#795` can move to fixed-local.

## Documentation Decision

Repository context changes because the temporal replay invariant now includes active-claim
supersession. No public OpenAPI, authored wiki, or operator-command contract changes.
