# CR-1690: Durable Enterprise Security-Audit Evidence

## Scope

- GitHub issue: #500
- Runtime owners: ingestion, query, query control plane, financial reconciliation, event replay
- Persistence owner: `portfolio_common.infrastructure.persistence.security_audit_store`
- Support owner: `GET /support/security-audit/events`

## Finding

The five protected Core HTTP applications emitted enterprise access events only through structured
logs. Log delivery could not prove that an authorization decision remained durable, and allowed
events were emitted after route execution, so downstream failures could erase the only evidence.
Concrete request paths and placeholder identities also risked turning unauthoritative request
material into apparent audit authority.

## Decision

Promoted profiles now append one typed PostgreSQL record before protected work executes. The closed
contract records the governed component, capability-rule route template, method, allow/deny reason,
policy version, bounded lineage, and verified signed identity. Unverified identity fields remain
SQL `NULL`; the implementation never substitutes `unknown` or `default`. Request bodies, query
strings, concrete paths, headers, arbitrary metadata, secrets, and raw exceptions are absent from
the table and response contract.

Audit persistence failure returns source-safe `503 security_audit_unavailable` before route
execution in staging, UAT, pre-production, and production profiles. Explicit local, development,
and test profiles retain log-only behavior so app-local work does not claim durable certification.
`LOTUS_CORE_PRODUCTION_SECURITY_PROFILE=false` cannot disable durable evidence or strict runtime
validation outside those explicit local profiles. Non-local `ENTERPRISE_AUDIT_READS=false` is
rejected during validation and cannot bypass defensive GET/HEAD persistence in middleware. Lazy
database/configuration failures are mapped
to the same safe failure contract. Delivery attempts increment `security_audit_delivery_total`
using only the bounded `service` and `outcome` labels.
Legacy structured logs remain compatibility diagnostics and now use governed templates or
`/unclassified`, not concrete paths.

QCP owns the protected `core.security_audit.read` support route. Tenant scope comes only from the
verified signed request context; callers cannot supply a tenant query parameter. Queries allow at
most 31 days and 200 records, use descending `(occurred_at, event_id)` keyset pagination, and map
database failure to a source-safe 503. Unverified denial rows remain durable but cannot be assigned
to a tenant without source authority.

Incoming correlation values longer than 128 characters are omitted from durable lineage. Trace
authority accepts only canonical W3C trace identifiers or a valid `traceparent`; malformed caller
text is never persisted. Oversized signed authority fields cause an auditable unverified denial
rather than an exception or truncated identity claim.

## Same-pattern review

The review covered the shared middleware plus all five protected app compositions, payload-size
denials, authorization denials, write allows, configured read allows, exception paths, route
templates, PostgreSQL error mapping, support response schemas, and OpenAPI. No other Core HTTP app
currently uses the enterprise readiness middleware. Alerting remains #501; retention, purge, and
legal-hold behavior remain #708. No historical log reconstruction or fabricated backfill is
permitted.

## Evidence

- 100 shared middleware, adapter, and service-composition tests passed.
- 103 domain, middleware, QCP router, and OpenAPI tests passed.
- Real PostgreSQL migration advanced `c156b2c3d523` through `c158b2c3d525`; the adapter proof passed
  four concurrent inserts, tenant isolation, same-timestamp keyset pagination, authority absence,
  and cleanup.
- Lazy runtime-configuration failures, a promoted-profile opt-out attempt, oversized signed
  lineage, and delivered/failed low-cardinality metric outcomes have focused regression proofs.
- Focused Ruff and MyPy checks passed for the touched runtime, application, and contract modules.
- Full repository-native, protected PR, and exact-main evidence remain required before #500 closes.

## Compatibility

This adds one table and one protected support endpoint. It does not change product request/response
DTOs, calculations, Kafka topics or partitioning, dependencies, framework versions, or deployable
topology. The intentional compatibility change is promoted-profile fail-closed behavior when the
durable audit database is unavailable. Repo-local and published operations wiki truth changes with
this slice.
