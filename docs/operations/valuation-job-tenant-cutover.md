# Valuation-job tenant authority cutover

Migration `c185b2c3d546` binds every retained portfolio valuation job to the canonical
tenant of its exact persisted portfolio root. Scheduling derives this authority from
`portfolios`; request headers, correlation IDs, and transport lineage cannot assign it.
The job's tenant/portfolio foreign key and tenant/portfolio/security/date/epoch unique
key enforce the same boundary in PostgreSQL.

## Coordinate the deployment

1. Drain portfolio valuation staging, the valuation scheduler, and position valuation
   calculators together. Include readiness, business-date, price, and FX producers that
   stage these jobs. Keep writers stopped through migration and code deployment.
2. Preserve pending transport messages and identify any older valuation messages without
   `tenant_id`. The new event contract refuses those messages. Resolve them through the
   existing failed-delivery process; do not invent tenant authority in a replay payload.
   Expired durable claims can be recovered and dispatched again with their persisted owner.
3. Apply the migration using the repository's configured database connection. It takes
   portfolio-root and job-table locks in that order, with a five-second lock timeout.
4. Deploy all valuation stagers, scheduler, and calculators from the same source revision,
   then resume them and verify pending work, lease recovery, and terminal outcomes.

Working directory: the `lotus-core` repository root. PowerShell:

```powershell
Set-Location "$env:LOTUS_WORKSPACE_ROOT/lotus-core"
make migration-apply
```

Bash:

```bash
cd "$LOTUS_WORKSPACE_ROOT/lotus-core"
make migration-apply
```

The migration refuses the whole transaction before changing job rows if an exact root
is absent, ambiguous, or has invalid retained tenant authority. Restore independently
verified source evidence before retrying. Never trim portfolio IDs, select a default
tenant, or delete retained jobs merely to pass the migration. Whitespace-distinct
portfolio IDs remain distinct. Job status, epochs, lease tokens, source-correction IDs,
and readiness sequences are preserved.

Downgrade also requires drained writers. It refuses any owned job groups that would
collapse under the previous unique key. The previous application contract cannot consume
the new tenant-bearing authority safely as a mixed-version deployment.

## Runtime authority and recovery

Global calendar, price, and FX observations remain global facts. Each staged portfolio
job acquires its owner from its exact portfolio root under a key-share lock. A missing
root refuses the entire scheduling batch before insertion. An already attributed request
with a conflicting tenant is refused.

Dispatch carries `tenant_id` in `PortfolioValuationRequiredEvent` and in typed recovery
receipts. Worker admission checks the exact tenant, portfolio, security, date, epoch,
processing state, claim token, and unexpired lease before idempotency or financial work.
Admission does not lock the job for the calculation's duration: source corrections can
still request requeue. The atomic terminal update repeats the tenant and lease fences;
losing ownership rolls back calculation effects. Dispatch recovery and stale recovery
retain tenant authority and cannot release another owner's claim.
Worker portfolio and position-history reads also bind the admitted tenant and exact
portfolio ID, so whitespace-distinct roots cannot mix their holdings or valuation context.

This slice relies on the existing globally unique portfolio root ID. It does not introduce
identical raw portfolio IDs across tenants. Readiness outbox records still use the existing
exact portfolio/security/date/epoch and sequence fence; tenant-owned outbox partitioning
and broader derived-record ownership remain separate #798 acceptance work. Financial
formulas and Kafka partition keys are unchanged.

## Validation

Use the repository-owned disposable test environment, separate from a live runtime.
From the repository root, the same commands apply in PowerShell and Bash:

```text
make coverage-shard-critical-db
make test-critical-lifecycle-db
```

The critical DB lane registers `test_valuation_job_tenant_postgresql.py`: exact retained
identities, duplicate staging, owner-specific supersession, foreign-key refusal, concurrent
claims, tenant-mismatched admission/terminal/recovery, lease expiry, and stale-token replay.
The lifecycle lane owns `test_valuation_job_tenant_migration.py`, which executes actual
Alembic upgrades and proves atomic refusal of orphan and trim-ambiguous history.
Existing readiness, source-correction, valuation persistence, and lease migration proofs
remain part of the regression boundary. Passing source tests does not certify a separate
live deployment or complete the wider #798 programme.
