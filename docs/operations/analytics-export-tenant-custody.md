# Analytics export tenant custody

Query Control Plane analytics exports bind durable access to the admitted `TenantId` and the
authoritative `Portfolio` owner. The request composition passes the same typed tenant to the
source reader and export repository. Request bodies, job identifiers and fingerprints do not
supply tenant authority.

Export creation admits the portfolio before reservation, including completed reuse, fresh
inflight reuse, stale replacement and refresh validation. Every primary job, fingerprint and
lifecycle lookup requires a matching portfolio owner through a correlated SQL predicate.
Creation separately checks primary ownership before adding or flushing a job. Foreign and
orphan jobs are invisible, including status, JSON, NDJSON and gzip retrieval. Missing and foreign
resources use the existing analytics not-found response without retained payload disclosure.

The portfolio identifier is globally unique and its non-null tenant is immutable through the
supported persistence upsert. No supported portfolio delete/recreate or reassignment operation
is part of this design. An out-of-band portfolio ownership rewrite must not be treated as a
supported tenant transfer: it would invalidate the ownership premise of retained exports.
Orphaned jobs fail closed; this change does not infer or repair their original ownership.
No export tenant column, migration, new endpoint or runtime service is introduced.

Owner completion, replay and correction semantics retain their existing request fingerprints
and payloads. Tenant access alone does not qualify source cuts, financial calculations,
institutional readiness or producer authority. Export capability admission remains a separate
control.

Focused source checks live in the owning export repository and analytics application unit tests.
Registered PostgreSQL controls in
`tests/integration/services/query_control_plane_service/test_analytics_tenant_postgresql.py`
cover both datasets, colliding fingerprints, foreign/missing/orphan reads, result formats,
refresh anchors, stale-job protection and lifecycle writes. They require the governed database
test lane; source tests alone do not establish live or PostgreSQL acceptance.
