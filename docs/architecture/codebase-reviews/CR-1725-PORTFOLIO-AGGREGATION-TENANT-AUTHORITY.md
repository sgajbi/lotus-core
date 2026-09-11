# CR-1725: Portfolio Aggregation Job Tenant Authority

## Scope

Review the durable `portfolio_aggregation_jobs` boundary under #798. The invariant is that every
job records the source-owned tenant of its portfolio and uses that same tenant for source reads,
lease-fenced terminal transitions and idempotent restaging.

## Finding

Aggregation work was durable and lease-fenced, but its identity was only portfolio and date. The
worker reloaded source state and finalized claims without tenant authority. This left a tenant-owned
derived-state boundary dependent on global portfolio identifiers.

## Correction

- Persist normalized, non-null tenant authority with a composite portfolio foreign key and
  tenant-aware job identity.
- Backfill only from the authoritative portfolio row and abort migration for orphaned work.
- Resolve tenant during staging, carry typed `TenantId` through claims and commands, and require it
  for source lookup and terminal ownership.
- Execute migration, tenant-positive, foreign-tenant, idempotency, recovery and concurrency proof in
  the protected critical database suite.
- Move the aggregate's constraints and indexes to `portfolio_aggregation_job_schema.py`, following
  the established owned-schema pattern. Ratchet the legacy ORM monolith from 5,566 to 5,511 lines.

## Preserved Boundaries

Aggregation dates, epochs, source revisions, correlations, lease semantics and financial outputs do
not change. Instrument, price, FX and business-calendar data remains deliberately global. Valuation
jobs, outbox, replay, DLQ and other durable tenant surfaces remain independently bounded #798 work.

## Evidence

- focused unit and documentation proof;
- PostgreSQL migration/backfill and full affected repository lifecycle proof;
- migration, architecture, tenant-ownership, source-size, maintainability and wiki gates;
- protected PR database execution, exact-main releasability and wiki parity required before closure.
