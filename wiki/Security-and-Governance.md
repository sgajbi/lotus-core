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
- source-data security profiles in
  `src/libs/portfolio-common/portfolio_common/source_data_security.py`

## Security posture to remember

- operator-facing support and evidence routes are intentionally governed and may carry stricter
  product posture than normal operational reads
- source-data products must keep access classification, audit requirements, and retention posture
  aligned with the RFC-0083 security target model
- capability and policy routes are part of the control plane and should not drift into ad hoc
  compatibility behavior or undocumented aliases
- duplicated service-local authorization or audit logic is a regression when the shared
  enterprise-readiness layer already owns it

## Operating rule

Governance in `lotus-core` is executable. If a contract or ownership rule matters, expect a guard,
registry, or test to enforce it.

## Related pages

- [Validation and CI](Validation-and-CI)
- [Query Control Plane](Query-Control-Plane)
- [RFC Index](RFC-Index)
