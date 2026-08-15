# CR-1692: Source-Safe Security-Audit Rehydration

## Scope

- GitHub issue: #954
- Persistence owner: `portfolio_common.infrastructure.persistence.security_audit_store`
- Application owner: query-control-plane security-audit query
- Delivery owner: `GET /support/security-audit/events`

## Finding

The PostgreSQL query adapter executed tenant-bound SQL safely but constructed strict
`SecurityAuditEvent` objects after leaving its database exception boundary. A database-valid row
with a non-canonical UUID, an unsupported domain enum, or non-normalized required text therefore
raised raw `ValueError`. The support router's caller-validation handler caught that error and
returned 422, falsely attributing corrupt durable evidence to a valid support query.

## Decision

Persisted-row conversion now has its own adapter boundary. Rehydration failures become
`InfrastructureAuditReadFailed`, a non-retryable typed database evidence error with bounded
diagnostics and no row identity or value. The application service preserves that type, and the QCP
router maps it with database unavailability to the documented source-safe 503 problem contract.
Only construction of `SecurityAuditQuery` can produce the caller-attributable 422 path.

The public success schema, filters, keyset cursor, table, migration head, and stored records remain
unchanged. OpenAPI and operator guidance now state that invalid caller bounds return 422, while a
database outage or persisted evidence that fails domain verification returns 503.

## Same-Pattern Review

The review searched Core infrastructure and service paths for strict domain rehydration helpers,
security-audit event construction, database-unavailability mapping, and broad route-level
`ValueError` handling. The durable enterprise security-audit adapter is the only Core persistence
adapter that constructs `SecurityAuditEvent`; no second audit/support adapter with this defect was
found. Other QCP `ValueError` handlers remain caller/application command validation and are outside
this evidence-specific correction.

## Evidence

- Unit tests cover database-valid-shaped rows with invalid UUID, component enum, and normalized
  required-field evidence; every case returns the same typed safe error and leaks no value.
- Application tests prove invalid cursors fail before store invocation while typed evidence-read
  failure crosses the service unchanged.
- Router and OpenAPI tests prove 422/503 attribution and stable RFC 9457/legacy response media.
- Real PostgreSQL proof persists a row accepted by table constraints but rejected by the domain UUID
  contract, then verifies typed failure, no partial page, and cleanup.
- Focused validation, full repository gates, PR evidence, and exact-main evidence are recorded on
  issue #954 as they complete.

## Compatibility

Successful 200 responses, query semantics, pagination, durable writes, database schema, migration
head, events, Kafka, calculations, dependencies, framework versions, and topology are unchanged.
The intentional correction is failure attribution: unreadable durable evidence returns 503 rather
than a caller-attributed 422. The operations wiki changes with this slice.
