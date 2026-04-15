# RFC-0083 Security, Tenancy, And Lifecycle Target Model

This document is the RFC-0083 Slice 9 target model for source-data product security, tenancy,
entitlement, audit, sensitivity, and retention posture in `lotus-core`.

It does not introduce new entitlement policy semantics, persistence changes, DTO payload changes, or
downstream response contract changes. The governed profile is exposed in OpenAPI route metadata so
consumers and contract guards can discover the required tenant, entitlement, audit, sensitivity, and
retention posture before runtime enforcement moves to gateway/platform ingress or service policy.

The executable helpers are:

1. `src/libs/portfolio-common/portfolio_common/source_data_security.py`
2. `tests/unit/libs/portfolio-common/test_source_data_security.py`
3. `src/libs/portfolio-common/portfolio_common/enterprise_readiness.py`
4. `tests/unit/libs/portfolio-common/test_enterprise_readiness_shared.py`
5. `src/services/query_service/app/enterprise_readiness.py`
6. `src/services/query_control_plane_service/app/enterprise_readiness.py`

## Target Principle

Every downstream-facing source-data product must be tenant-scoped, entitlement-scoped, auditable, and
classified for sensitivity and retention before it becomes a production contract.

`lotus-core` owns the source truth, but it should not become the global authorization engine. Runtime
authorization may be delegated to platform ingress or gateway policy, but `lotus-core` contracts must
declare the required security posture explicitly.

## Required Profile Fields

Every source-data product profile must define:

1. `product_name`,
2. tenant scoping requirement,
3. entitlement scoping requirement,
4. access classification,
5. sensitivity classification,
6. retention requirement,
7. audit requirement,
8. PII/client-sensitive fields where applicable,
9. whether the product is operator-only.

The helper validates that every product in the Slice 6 source-data product catalog has a profile and
emits the `x-lotus-source-data-security` OpenAPI extension for catalog-backed routes. It also
prevents operator-only products from being classified outside the control-plane and policy route
family, so support and evidence products cannot silently drift into business read or analytics-input
contracts. Access classifications are route-family constrained: business-consumer access belongs to
operational read or snapshot/simulation products, system access belongs to analytics-input products,
and operator access belongs to control-plane and policy products. Audit requirements are constrained
the same way: business-consumer products use read/export audit, system products use system-access
audit, and operator products use operator-access audit. Retention requirements are constrained by
sensitivity class: client-confidential and client-sensitive products use client-record retention,
reference-internal products use source-audit retention, and internal-operational products use
operational-audit retention.

## Access Classes

| Class | Meaning |
| --- | --- |
| `business_consumer_access` | Product may be consumed by governed downstream business surfaces |
| `system_access` | Product is intended for service-to-service analytics or reference workflows |
| `operator_access` | Product is support/operator evidence and should not be exposed as a normal business product |

## Sensitivity Classes

| Class | Meaning |
| --- | --- |
| `client_confidential` | Portfolio/client source truth with confidentiality impact |
| `client_sensitive` | Client-linked transactional or activity data |
| `reference_internal` | Reference/market data whose source license and lineage matter |
| `internal_operational` | Operational, evidence, or support data with incident/audit sensitivity |

## Retention And Audit

| Requirement | Meaning |
| --- | --- |
| `retain_for_client_record` | Keep according to client/account/portfolio books-and-records policy |
| `retain_for_source_audit` | Keep according to vendor/source-data replay and licensing audit policy |
| `retain_for_operational_audit` | Keep according to incident, replay, reconciliation, and operator evidence policy |

Audit requirements are:

1. `audit_read_and_export` for client-facing source products,
2. `audit_system_access` for service-to-service analytics/reference products,
3. `audit_operator_access` for support and evidence products.

## Runtime Follow-Up

Future runtime slices must:

1. expose tenant and policy context where missing,
2. apply entitlement checks at gateway/platform ingress or service policy before source products are
   returned,
3. audit export and operator-evidence access,
4. redact or suppress sensitive fields where caller policy does not permit access,
5. add migration smoke only when persistence changes,
6. update downstream consumer tests when authorization or field visibility changes.

`PortfolioAnalyticsReference` follows the analytics-input system-access posture but remains
`client_confidential` because it exposes portfolio identity and client linkage needed by downstream
analytics services. It requires tenant scoping, entitlement scoping, system-access audit, and
client-record retention rather than operator-only evidence handling.

## Runtime-Contract Binding

Every catalog-backed source-data product route now exposes two machine-readable OpenAPI extensions:

1. `x-lotus-source-data-product` for product identity, ownership, serving plane, consumers, and
   required supportability metadata,
2. `x-lotus-source-data-security` for tenant scoping, entitlement scoping, access class, sensitivity
   class, retention requirement, audit requirement, PII/client-sensitive field markers, and
   operator-only posture.

`scripts/source_data_product_contract_guard.py` verifies that the OpenAPI metadata emitted by
`source_data_product_openapi_extra(...)` matches the governed security profile. This is contract
readiness proof, not runtime authorization enforcement.

## Shared Runtime Support

`query_service` and `query_control_plane_service` now use the shared
`portfolio_common.enterprise_readiness` runtime for enterprise policy version headers, write payload
limits, optional write authorization checks, capability-rule matching, feature-flag lookup,
sensitive audit metadata redaction, write audit event emission, opt-in read audit event emission
when `ENTERPRISE_AUDIT_READS=true`, and opt-in read authorization when
`ENTERPRISE_ENFORCE_READ_AUTHZ=true`.

Each service keeps a local `enterprise_readiness.py` wrapper so existing imports, tests, settings,
and service-specific patch points remain stable. The shared helper removes duplicated middleware
logic and gives future runtime security work one implementation point, but it does not by itself
claim production entitlement enforcement closure.

Read auditing is intentionally disabled by default until platform ingress and gateway policy decide
the production audit volume and storage posture. When enabled, the middleware records the route path,
status code, actor, tenant, role, correlation id, and access type without copying request bodies or
query-string values into audit metadata.

Read authorization is also disabled by default. When enabled, GET and HEAD requests must provide the
same actor, tenant, role, correlation, and service identity context required for write authorization,
and may be checked against `ENTERPRISE_CAPABILITY_RULES_JSON` entries such as
`GET /integration/portfolios`. This is service-policy support; full production entitlement closure
still requires gateway/platform ingress policy proof and affected-consumer validation.

When production policy requires explicit entitlement rules, `ENTERPRISE_REQUIRE_CAPABILITY_RULES=true`
can be enabled alongside read or write authorization. In that mode, any protected request without a
matching method/path capability rule is denied with `missing_capability_rule`, and runtime
configuration validation reports `missing_capability_rules` if no capability rules are configured.

## Validation

Slice 9 validation is:

1. `python -m pytest tests/unit/libs/portfolio-common/test_source_data_security.py -q`,
2. `python -m pytest tests/unit/libs/portfolio-common/test_source_data_products.py tests/unit/scripts/test_source_data_product_contract_guard.py -q`,
3. `python -m pytest tests/unit/libs/portfolio-common/test_enterprise_readiness_shared.py tests/unit/services/query_service/test_enterprise_readiness.py tests/unit/services/query_control_plane_service/test_control_plane_enterprise_readiness.py -q`,
4. `python scripts/source_data_product_contract_guard.py`,
5. `python -m pytest tests/integration/services/query_service/test_main_app.py tests/integration/services/query_control_plane_service/test_control_plane_app.py -q`,
6. `python -m ruff check src/libs/portfolio-common/portfolio_common/source_data_security.py src/libs/portfolio-common/portfolio_common/source_data_products.py src/libs/portfolio-common/portfolio_common/enterprise_readiness.py src/services/query_service/app/enterprise_readiness.py src/services/query_control_plane_service/app/enterprise_readiness.py scripts/source_data_product_contract_guard.py tests/unit/libs/portfolio-common/test_source_data_security.py tests/unit/libs/portfolio-common/test_source_data_products.py tests/unit/libs/portfolio-common/test_enterprise_readiness_shared.py tests/unit/scripts/test_source_data_product_contract_guard.py --ignore E501,I001`,
7. `python -m ruff format --check src/libs/portfolio-common/portfolio_common/source_data_security.py src/libs/portfolio-common/portfolio_common/source_data_products.py src/libs/portfolio-common/portfolio_common/enterprise_readiness.py src/services/query_service/app/enterprise_readiness.py src/services/query_control_plane_service/app/enterprise_readiness.py scripts/source_data_product_contract_guard.py tests/unit/libs/portfolio-common/test_source_data_security.py tests/unit/libs/portfolio-common/test_source_data_products.py tests/unit/libs/portfolio-common/test_enterprise_readiness_shared.py tests/unit/scripts/test_source_data_product_contract_guard.py`,
8. `git diff --check`,
9. `make lint`.
