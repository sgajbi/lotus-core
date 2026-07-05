# Security and Governance

## Main governance surfaces

- RFC-0082 contract-family placement
- RFC-0083 target-state hardening
- source-data product security and lifecycle posture
- event-runtime supportability governance
- temporal vocabulary and route-family guards
- enterprise-readiness authorization, policy-header, capability, and audit middleware reuse

## Important references

- [Architecture Index](../docs/architecture/README.md)
- [RFC-0082 Contract Family Inventory](../docs/architecture/RFC-0082-contract-family-inventory.md)
- [RFC-0083 Security Tenancy Lifecycle Target Model](../docs/architecture/RFC-0083-security-tenancy-lifecycle-target-model.md)
- [RFC-0083 Eventing Supportability Target Model](../docs/architecture/RFC-0083-eventing-supportability-target-model.md)
- [Temporal Vocabulary](../docs/standards/temporal-vocabulary.md)
- [Route Contract-Family Registry](../docs/standards/route-contract-family-registry.json)

## What is actually enforced

Governance in `lotus-core` is not just a document set.

It is enforced through:

- route-family registry and route-family guard
- source-data product metadata and consumer guards
- event-runtime contract guard
- RFC-0083 closure guard
- OpenAPI and architecture guards
- generated `x-lotus-source-data-security` route metadata
- shared enterprise-readiness helpers in
  `src/libs/portfolio-common/portfolio_common/enterprise_readiness.py`
- ingestion write capability rules in
  `src/services/ingestion_service/app/enterprise_readiness.py`
- shared production-security profile selection in
  `src/libs/portfolio-common/portfolio_common/runtime_settings.py`
- source-data security profiles in
  `src/libs/portfolio-common/portfolio_common/source_data_security.py`
- FastAPI app security-control coverage in
  `contracts/security/security-control-coverage.v1.json`

## HTTP app security controls

`make security-control-coverage-guard` checks that every FastAPI app is listed in the governed
matrix and has implementation anchors for:

- shared HTTP bootstrap
- secure response headers
- deny-by-default CORS
- trusted-host enforcement
- metrics access policy
- enterprise auth/audit middleware on business and operator APIs
- unauthenticated health and metrics allowlist
- payload limits and ingestion upload byte limits where relevant
- safe unhandled-error responses

For `ingestion_service`, the service-owned enterprise wrapper is also the default source of
capability truth for canonical write routes. New `/ingest/*` or `/reprocess/*` write routes must
add a route capability rule and keep the route-coverage test green; production-like deployments
should not rely only on environment JSON to protect normal ingestion writes.

This is static repository evidence. Live ingress, IAM, WAF, network policy, and penetration-test
proof remain separate higher-lane evidence.

## Production security profile

Production-like Core environments default service-local enterprise controls to fail closed.
`prod`, `production`, `preprod`, `pre-prod`, `pre-production`, `staging`, `stage`, and `uat`
enable:

- write authorization
- read authorization
- read audit emission
- capability-rule enforcement
- runtime configuration enforcement

Local, dev, and test environments remain opt-in. A time-bound production-profile opt-out must be
explicit through `LOTUS_CORE_PRODUCTION_SECURITY_PROFILE=false` and should be treated as deployment
posture evidence, not as a code default.

## Security posture to remember

- operator-facing support and evidence routes are intentionally governed and may carry stricter
  product posture than normal operational reads
- source-data products must keep access classification, audit requirements, and retention posture
  aligned with the RFC-0083 security target model
- capability and policy routes are part of the control plane and should not drift into ad hoc
  compatibility behavior or undocumented aliases
- duplicated service-local authorization or audit logic is a regression when the shared
  enterprise-readiness layer already owns it
- production-like deployments should not depend on hand-written per-service auth/audit defaults;
  use the shared production-security profile helper
- source-of-truth write planes need service-owned default capability maps plus tests that cover
  every registered write route
- query-service cursor/page tokens must use the shared versioned `PageTokenCodec` envelope with
  `kid`, expiry, issuer/audience, optional route/tenant binding, and previous-key rotation support
- production-like HTTP services must set non-wildcard `LOTUS_HTTP_TRUSTED_HOSTS`; the local `*`
  trusted-host default is only for local/dev/test compatibility
- new FastAPI apps must be added to the security-control matrix in the same slice as their
  bootstrap path, or `make lint` will fail

## Operating rule

Governance in `lotus-core` is executable. If a contract or ownership rule matters, expect a guard,
registry, or test to enforce it.

## Related pages

- [Validation and CI](Validation-and-CI)
- [Query Control Plane](Query-Control-Plane)
- [RFC Index](RFC-Index)
