# CR-1695 Bounded Database Statement Batching

Status: merged and exact-main validated

## Objective

Close GitHub issue #511 by ensuring that caller-sized valuation and reprocessing collections never
become one unbounded PostgreSQL `VALUES`, scalar `IN`, or tuple `IN` statement. Preserve financial
state, epoch fencing, watermark, lease, result-cardinality, and caller-owned transaction semantics.

## Decision And Ownership

`portfolio_common.infrastructure.persistence.statement_batching` owns one physical statement
policy:

- at most 1,000 rows per statement;
- at most 32,000 bind parameters after reserved statement binds;
- an effective row limit calculated from the operation's complete per-row bind width;
- invalid widths or budgets rejected before repository I/O; and
- input order preserved by the chunk iterator.

Each repository remains responsible for validating and globally normalizing its domain input before
chunking. Position-state identities are `(portfolio_id, security_id, expected_epoch)`; identical
updates collapse and conflicting watermark/status updates fail before SQL. Dispatch-recovery claims
collapse only when the same job retains the same claim token; conflicting token authority fails
before SQL. Read keys are globally deduplicated and sorted. This common lock order prevents caller
ordering from creating an inverted lock sequence across chunks.

Repositories stage every chunk on the injected `AsyncSession`. They do not commit, roll back,
create a nested transaction, or acquire a separate connection. A later-chunk failure therefore
propagates to the caller's unit of work, which can roll back the entire logical operation.

## Covered Operations

The bounded contract applies to:

1. position-state bulk epoch-fenced updates;
2. position watermark reset/touch predicates;
3. valuation-job upsert and latest-epoch lookup;
4. first-open-position-date lookup;
5. contiguous-snapshot-date evaluation, including its `VALUES` source table; and
6. scheduler dispatch-failure recovery updates;
7. expired valuation-claim classification and supersede/fail/reset updates; and
8. stale reprocessing-job classification and fail/reset updates.

Both stale-recovery readers select at most 1,000 rows in deterministic order per invocation. A
remaining backlog is drained by later scheduler polls. Update helpers also normalize and chunk
defensively, so direct reuse cannot bypass the statement policy. Effective-dated replay identity
coalescing remains per job inside the same caller transaction; only its input cohort is bounded.

The prior valuation-job-only 1,000-row helper was removed and folded into the shared persistence
authority. Staging tables or `COPY` are intentionally excluded until #510 provides plan and row-count
evidence that bounded statements are insufficient.

## Operability

An oversized operation emits one structured `database_statement_batch` event with governed
`operation`, `status`, and `reason_code` values plus normalized item count, statement count, and
maximum rows per statement. It is emitted once per logical operation, not once per chunk.
Portfolio, security, job, claim, correlation, and other business identifiers are not fields or
labels. Stale-recovery warnings likewise publish bounded counts and reason codes rather than job-ID
collections.

## Compatibility

There is no API, OpenAPI, event/Kafka, calculation, database schema/migration, dependency, image,
datastore, or topology change. Valid method signatures, returned counts/maps, epoch and watermark
semantics, lease predicates, scheduler behavior, and one caller-owned transaction are preserved.
The only intentional behavioral tightening is deterministic rejection of conflicting duplicate
updates or claim tokens that previously made SQL results order-dependent.

## Same-Pattern Boundary

The full repository audit proved existing explicit bounds for market-price source facts and
valuation-policy assignments. Distinct unbounded families were durably routed rather than absorbed:

- transaction-economics persistence and receipt reconstruction remain owned by #719;
- estate-wide reconciliation reads remain owned by #503; and
- public DPM market-data coverage cardinality and adapter batching are owned by #961; and
- aggregation-owned expired-lease recovery batching is owned by #962.

This review does not claim repository-wide elimination of every tuple predicate.

## Validation Evidence

- warning-strict focused batching, position-state, valuation-job, and repository tests pass;
- MyPy passes across 318 source files;
- PostgreSQL tests cover 1,001-row statement count, second-chunk rollback, overlapping reverse-order
  transactions, and a 10,000-row/ten-statement cohort;
- existing PostgreSQL semantics tests continue to cover epoch fencing, earliest watermark, first
  open date, contiguous snapshots, and dispatch recovery; and
- PR #964 merged by governed rebase at exact main
  `5b51f6e1387e2881c0c25a1d48040aa519b8f5a1`; companion PR #965 corrected the deterministic
  readiness-query oracle at `5aeb6b5e11bfeb7ed81670e0e38f5a09d642f472`.
- Main Releasability run `32436643792` passed at exact main
  `577dba8ea08182355a262004937dd693fe46ac04`, including combined coverage, complete integration,
  exact-source images, full E2E, performance, latency, and failure recovery.
- The authored Operations wiki is published through
  `9fa7545271bd490a6ac55aa6023f5a150b8e6229` with strict parity zero. Branch/worktree reconciliation
  left one clean Core worktree on `main` and no merged feature branch.
