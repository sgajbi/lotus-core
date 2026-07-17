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
   different correction lineage meets a `PROCESSING` natural-key valuation job, the row retains
   its active status and records one durable requeue request. The active owner atomically returns
   the row to `PENDING` and reports that it did not complete, preventing publication of the stale
   snapshot. Same-lineage and ordinary readiness duplicates remain non-disruptive. Stale-claim and
   dispatch recovery consume the same fence without dropping a correction at the retry limit.

## Compatibility

Public APIs, persisted source-event schemas, Kafka topics, and position valuation formulas are
unchanged. Migration `c114b2c3d4f3` adds one non-null, false-defaulted internal queue-fence column.
The intentional internal behavior change removes redundant current-date replay while preserving a
newer correction that races with active valuation work. Backdated and future correction contracts
remain unchanged.

## Validation

- `97` valuation-orchestrator unit tests passed.
- `3` focused PostgreSQL price/FX freshness lifecycle tests passed.
- Review fix-forward proof added `48` focused unit checks and `2` isolated PostgreSQL queue
  lifecycle scenarios: same-lineage source delivery remains a no-op, while a different correction
  stays fenced during `PROCESSING`, causes the stale owner to return false, and becomes `PENDING`
  under the newer correlation.
- Focused Ruff lint and format checks passed.
- Full repository `make typecheck` passed for `235` source files.
- Architecture boundary, domain layer, application workflow policy, and infrastructure adapter
  guards passed.

The implementation commits are `4b8a4c772` and `fd7c71fa5`; the in-flight correction fix-forward
commit is recorded after signing. The prior failed certifying artifact is
`output/task-runs/20260716T095705Z-bank-day-load.json`. An initial local lifecycle attempt reused a
prebuilt migration image at Alembic head `c113b2c3d4f2` and failed because the `c114b2c3d4f3`
column was absent; it is invalid harness evidence, not a behavior verdict. The branch-local
migration image and governed `unit-db` rerun passed. Fresh runtime evidence remains required before
issue `#795` can move to fixed-local.

## Documentation Decision

Repository context changes because the temporal replay invariant now includes active-claim
supersession. No public OpenAPI, authored wiki, or operator-command contract changes.
