# CR-1717: Tenant-Owned Analytics Export Lifecycle

## Scope

GitHub issue `#798` S1 and the latest PR review identified a P1 isolation defect in the Query
Control Plane analytics-export lifecycle. Export rows had no durable tenant owner, so globally
unique-looking job IDs and request fingerprints acted as de facto authorization for reuse,
status/result access, and lifecycle mutation. The adjacent operator job listing was portfolio-only.

## Financial and security invariant

An analytics export may contain authoritative portfolio evidence. Every durable export row and
every read or mutation of that row must therefore be attributable to the immutable tenant admitted
at the enterprise HTTP boundary. Job IDs, portfolio IDs, and fingerprints are lookup keys only;
they are never tenant authority. A foreign identifier must be indistinguishable from an absent one.

## Implementation

- Added non-blank `tenant_id` to `analytics_export_jobs` and a composite foreign key to
  `portfolios(tenant_id, portfolio_id)`.
- Added a fail-closed migration that backfills only from authoritative portfolio ownership and
  aborts with bounded diagnostics when any row cannot be attributed.
- Tenant-scoped creation, fingerprint reuse, lifecycle transitions, status reads, and JSON/NDJSON
  result retrieval through the application port and repository.
- Required owned-portfolio evidence before reservation so a foreign request cannot create or reuse
  a job.
- Tenant-scoped the operator analytics-export count/page queries and ownership preflight using the
  admitted request context.
- Extended the tenant-ownership guard so future removal or optionalization of these tenant
  parameters fails CI.

## Compatibility

Public success DTOs and lifecycle semantics are unchanged. Foreign job and portfolio identifiers
now return the established not-found behavior. Fingerprint reuse is intentionally limited to one
tenant. The schema migration is additive before enforcement and reversible; it never creates a
synthetic tenant.

## Proof

- Focused repository, service, router, domain, ORM, migration, and guard tests.
- Real PostgreSQL fail-closed orphan detection and recovery, backfill, composite-ownership
  rejection, cross-tenant lookup, fingerprint, and lifecycle-mutation proof.
- Repository-native lint, type, architecture, migration, documentation, and test gates are recorded
  on PR `#1076` before merge.

## Remaining issue-backed scope

Issue `#798` remains open for its later tenant-isolation slices, including the broader operations
support/readiness family. This review does not claim that those remaining surfaces are complete.
