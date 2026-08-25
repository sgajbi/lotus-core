# CR-1711: Reprocessing Job Lease Isolation

Date: 2026-08-25

## Scope

Resolve GitHub issue #998 for durable `RESET_WATERMARKS` and `RESET_FX_WATERMARKS` execution without
changing product APIs, replay ordering, coalescing identity, financial calculations, Kafka
contracts, or runtime topology.

## Finding

`ReprocessingWorker` claimed, executed, and terminalized a whole reset/FX batch inside one database
transaction. One database failure could roll back sibling claims and completed work. Ownership was
inferred from `status='PROCESSING'` and `updated_at`, so a recovered job had no opaque fence against
a late worker.

## Action

- Added additive owner/token/database-clock-expiry authority and a partial ordered recovery index.
- Made the schema cutover fail closed unless the old queue is quiesced; downgrade also rejects
  active leased work.
- Return immutable claimed records instead of transaction-bound ORM instances.
- Commit recovery separately; claim each reset or FX job immediately before execution; execute every
  job in its own transaction; and write FAILED state in a fresh transaction after rollback. This
  prevents serially waiting siblings from expiring before their work starts.
- Preserve raw database JSON through claim mapping so a malformed legacy payload is rejected and
  terminalized inside its own job boundary rather than rolling back the whole claim transaction.
- Require exact token and unexpired PostgreSQL-clock lease for COMPLETE, PENDING, or FAILED writes.
- Renew live claims every one-third lease interval in an independent transaction; cancel and roll
  back active domain work immediately when renewal loses authority.
- Return typed transition outcomes so expiry, token mismatch, missing work, and terminal-state races
  remain operationally distinguishable; reject empty FAILED reasons.
- Recover expired claims under deterministic `FOR UPDATE SKIP LOCKED` cohorts while preserving
  attempt count and existing effective-date coalescing semantics.

## Result

A failed or malformed job cannot roll back or block a sibling. A lease begins only when its job is
next to execute, eliminating expiry caused solely by waiting behind slower serial work. Expired work
can be deterministically recovered and reclaimed, while the former worker cannot commit either
terminal state or transaction-scoped domain mutations. Claim attempts remain durable and auditable
across recovery.

## Evidence

- Real PostgreSQL migration upgrade/guard/constraint/downgrade proof.
- Real PostgreSQL claim concurrency, expiry recovery, reclaim, token-fence, attempt, FX, and
  conversion regression tests.
- Real PostgreSQL worker proof that a forced server-side division-by-zero abort exits the first job
  transaction, records FAILED in a fresh session, and does not prevent the sibling terminal commit.
- Unit proof that heartbeat renewal succeeds independently and that renewal ownership loss cancels
  the active operation.
- Unit proof that a second reset job is not claimed until the first finishes, malformed reset JSON
  fails independently without blocking a valid sibling, and non-object FX JSON reaches the governed
  rejected-job path. PostgreSQL integration proof preserves JSON `null` in one claimed record while
  returning its valid sibling from the same claim.
- `make typecheck`, architecture guard, repository transaction-boundary guard, and testability
  architecture guard passed.
- `make database-hot-path-evidence` completed; the three #998 acceptance scenarios
  (`reprocessing_job_claim`, `reprocessing_stale_scan`, and `reprocessing_stale_reset`) passed. The
  report-only aggregate remains failed only on pre-existing claim-normalization (#988) and
  transaction-ledger scenarios outside #998.

## Contract Decisions

- No API, OpenAPI, event, Kafka, calculation, dependency, image, datastore, framework, or runtime
  topology change.
- Repo-local operations and engineering context changed; wiki source changed and must be published
  after merge.
- No new skill is required. Platform issue #677 already owns reusable database-clock lease guidance;
  this slice applies that governed pattern and should cross-link its evidence rather than duplicate
  skill authority locally.
