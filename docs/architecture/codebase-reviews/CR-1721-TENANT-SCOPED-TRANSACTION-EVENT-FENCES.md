# CR-1721 Tenant-Scoped Transaction Event Fences

Date: 2026-09-07  
Issue: #798 tranche B  
Status: Fixed-local candidate

## Invariant

An admitted transaction belongs to exactly one source-owned tenant. Two tenants may legitimately
use the same transport event identifier or transaction semantic key; those facts must not suppress
one another. Within one tenant, physical duplicates, semantic duplicates, material conflicts, and
transaction rollback/retry remain deterministic.

## Correction

- `TransactionEvent` now requires a normalized `tenant_id`; ingestion supplies only the tenant
  admitted in `TenantContext`.
- Persistence verifies the event's portfolio against that tenant and carries the tenant into its
  processed-event claim.
- Transaction processing and its cashflow side-effect fence use the same tenant dimension. Tenant
  remains outside the payload fingerprint because it is a durable natural-key dimension, not a
  mutable booking input.
- `processed_events` retains nullable tenant attribution for deliberately global market-data
  families. Separate partial unique indexes protect tenant-owned and global physical and semantic
  keys. Transaction service families cannot store a null tenant.
- Migration `c167b2c3d52e` backfills known transaction fences from authoritative portfolio
  ownership and aborts on unattributable rows. Downgrade aborts before mutation when cross-tenant
  collisions cannot fit the former global key.
- Replay restores transaction tenant authority by joining the owning portfolio. Internal database
  rows use an explicit persisted-record mapper instead of being presented as transport events.

## Proof

Real PostgreSQL tests reproduce same-key claims for two tenants, same-tenant concurrency,
duplicate/conflict classification, rollback/retry, fail-closed legacy backfill, and unsafe downgrade.
Focused event, ingestion, persistence, processing, cashflow, replay, and mapping tests cover the
request-to-fence path. Repository-native lint, architecture/event guards, and MyPy pass. The full
unit warning gate passed 9,702 tests with zero warnings except for the pre-existing Windows
repository-launcher isolation failure recorded on the PR.

## Remaining Scope

This does not certify estate-wide tenant isolation. #798 still owns outbox tenant/partition
authority, tenant-safe durable transaction and derived-state identity, valuation/timeseries/
reconciliation tenancy, replay/DLQ/operator controls, and final collision certification. Global
price and FX event fences intentionally remain global in this tranche.

No shared skill change is required: the backend delivery contract already requires cross-scope
collision proof, fail-closed migration, deterministic replay, and durable authority. This review
records the Core-specific application of that rule.
