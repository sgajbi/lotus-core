# RFC-0083 Security, Tenancy, And Lifecycle Target Model

This document is the RFC-0083 Slice 9 target model for source-data product security, tenancy,
entitlement, audit, sensitivity, and retention posture in `lotus-core`.

It does not introduce persistence changes, DTO payload changes, or downstream response contract
changes. The governed profile is exposed in OpenAPI route metadata so consumers and contract guards
can discover the required tenant, entitlement, capability, audit, sensitivity, and retention posture
before production enforcement moves to gateway/platform ingress or service policy.

The executable helpers are:

1. `src/libs/portfolio-common/portfolio_common/source_data_security.py`
2. `tests/unit/libs/portfolio-common/test_source_data_security.py`
3. `src/libs/portfolio-common/portfolio_common/enterprise_readiness.py`
4. `tests/unit/libs/portfolio-common/test_enterprise_readiness_shared.py`
5. `src/services/query_service/app/enterprise_readiness.py`
6. `src/services/query_service/app/settings.py`
7. `tests/unit/services/query_service/test_enterprise_readiness.py`
8. `tests/unit/services/query_service/test_query_service_settings.py`
9. `src/services/query_control_plane_service/app/enterprise_readiness.py`
10. `src/services/query_control_plane_service/app/settings.py`
11. `tests/unit/services/query_control_plane_service/test_control_plane_enterprise_readiness.py`
12. `tests/unit/services/query_control_plane_service/test_control_plane_settings.py`

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
8. governed read capability,
9. PII/client-sensitive fields where applicable,
10. whether the product is operator-only.

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
   class, retention requirement, audit requirement, governed read capability, PII/client-sensitive
   field markers, and operator-only posture.

`scripts/source_data_product_contract_guard.py` verifies that the OpenAPI metadata emitted by
`source_data_product_openapi_extra(...)` matches the governed security profile. This is contract
readiness proof and keeps the published capability requirement aligned with the catalog.

## Shared Runtime Support

`query_service`, `query_control_plane_service`, and `ingestion_service` now use typed or
service-local settings plus the shared `portfolio_common.enterprise_readiness` runtime for
enterprise policy version headers, write payload limits, write authorization checks,
capability-rule matching, feature-flag lookup, sensitive audit metadata redaction, write audit event
emission, read audit event emission, read authorization, and strict capability-rule enforcement.

Local/dev/test environments remain opt-in for read authorization, read auditing, capability-rule
enforcement, and runtime-config enforcement. Production-like environments now use the shared
production security profile in `portfolio_common.runtime_settings`: `prod`, `production`,
`preprod`, `pre-prod`, `pre-production`, `staging`, `stage`, and `uat` default
`ENTERPRISE_ENFORCE_AUTHZ`, `ENTERPRISE_ENFORCE_READ_AUTHZ`, `ENTERPRISE_AUDIT_READS`,
`ENTERPRISE_REQUIRE_CAPABILITY_RULES`, and `ENTERPRISE_ENFORCE_RUNTIME_CONFIG` to true unless
`LOTUS_CORE_PRODUCTION_SECURITY_PROFILE=false` is set explicitly. This makes service-local
production posture fail closed while preserving local developer compatibility.

The shared runtime now derives default read capability rules directly from the source-data product
catalog and security profiles. Each catalog route receives `GET` and `POST` read capability rules
using `source_data.<product_name_snake_case>.read`, for example
`source_data.portfolio_analytics_reference.read`. This covers query-style `POST` endpoints such as
analytics-input routes, so enabling read authorization protects source-data products even when the
request method is `POST`. `ENTERPRISE_CAPABILITY_RULES_JSON` can still add or override rules, but
production source-data routes no longer rely on hand-written environment mappings before strict mode
can be enabled.

Services with source-of-truth write planes may also provide service-owned default capability rules.
`ingestion_service` uses this mechanism for canonical `/ingest/*` and `/reprocess/*` write routes
with route-family capabilities such as `ingestion.portfolios.write`,
`ingestion.transactions.write`, and `ingestion.reference_data.write`. Future ingestion write routes
must update the service-owned map and keep the route-coverage test green; production policy must not
depend only on environment JSON for normal write-plane authorization.

The shared enterprise middleware has an explicit unauthenticated operational allowlist for
`/health/live`, `/health/ready`, `/metrics`, `/openapi.json`, `/docs`, `/redoc`, and `/version`.
This preserves probe, metrics, API documentation, and version access under read-authorization
enforcement while keeping business and operator routes protected by capability rules.

Privileged ingestion operations may accept bearer JWTs, but the policy is intentionally stricter
than local static-token compatibility. JWTs must include `exp`, `iat`, `iss`, `aud`, `jti`, one
principal identity claim from `sub`, `client_id`, or `azp`, the configured ops scope/capability,
and `kid`. The ingestion ops verifier supports an active HS256 key plus previous keys for rotation.
Production-like and strict profiles must configure JWT issuer, audience, active key id, active
secret, and required scope; static `X-Lotus-Ops-Token` fallback requires explicit non-local
approval and a non-default token.

Each service keeps a local `enterprise_readiness.py` wrapper so existing imports, tests, settings,
and service-specific patch points remain stable. The shared helper removes duplicated middleware
logic and gives future runtime security work one implementation point, but it does not by itself
claim production entitlement enforcement closure.

Read auditing records the route path, status code, actor, tenant, role, correlation id, and access
type without copying request bodies or query-string values into audit metadata. It remains opt-in in
local/dev/test environments and default-on in the production security profile.

Read authorization requires GET and HEAD requests to provide the same actor, tenant, role,
correlation, and service identity context required for write authorization. Catalog-backed
source-data `POST` requests must provide the same context when they match a governed source-data
product capability rule. Requests may also be checked against `ENTERPRISE_CAPABILITY_RULES_JSON`
entries such as `GET /integration/portfolios`, but source-data products already have
catalog-derived defaults. This is service-policy support; full production entitlement closure still
requires gateway/platform ingress policy proof and affected-consumer validation.

The service identity and capability context must be verified before it is trusted. The shared
enterprise middleware accepts capabilities only from the signed internal auth-context contract:
`X-Enterprise-Auth-Key-Id`, `X-Enterprise-Auth-Timestamp`, and
`X-Enterprise-Auth-Signature` bind actor, tenant, role, correlation id, service identity, timestamp,
key id, and normalized capabilities. `Authorization` and `X-Service-Identity` headers are not
presence markers for entitlement; an unsupported bearer token or unsigned service identity is denied
when enterprise authorization is enabled. `ENTERPRISE_AUTH_CONTEXT_HMAC_SECRET` and
`ENTERPRISE_AUTH_CONTEXT_MAX_AGE_SECONDS` configure the trusted gateway or mTLS boundary.

When production policy requires explicit entitlement rules, `ENTERPRISE_REQUIRE_CAPABILITY_RULES=true`
can be enabled alongside read or write authorization. In that mode, any protected request without a
matching method/path capability rule is denied with `missing_capability_rule`, and runtime
configuration validation reports `missing_capability_rules` if no actionable catalog-derived or
configured capability rules are available. Actionable rules must use a supported read/write method,
an absolute route path or FastAPI-style path template, and a non-empty capability name, for example
`GET /integration/portfolios/{portfolio_id}/analytics/reference` mapped to
`source_data.portfolio_analytics_reference.read`.

## Validation

Slice 9 validation is:

1. `python -m pytest tests/unit/libs/portfolio-common/test_source_data_security.py -q`,
2. `python -m pytest tests/unit/libs/portfolio-common/test_source_data_products.py tests/unit/scripts/test_source_data_product_contract_guard.py -q`,
3. `python -m pytest tests/unit/libs/portfolio-common/test_enterprise_readiness_shared.py tests/unit/services/query_service/test_enterprise_readiness.py tests/unit/services/query_service/test_query_service_settings.py tests/unit/services/query_control_plane_service/test_control_plane_enterprise_readiness.py tests/unit/services/query_control_plane_service/test_control_plane_settings.py tests/unit/services/ingestion_service/test_enterprise_readiness.py -q`,
4. `python scripts/source_data_product_contract_guard.py`,
5. `python -m pytest tests/integration/services/query_service/test_main_app.py tests/integration/services/query_control_plane_service/test_control_plane_app.py -q`,
6. `python -m pytest tests/integration/services/ingestion_service/test_ingestion_main_app_contract.py -q`,
7. `python -m ruff check src/libs/portfolio-common/portfolio_common/source_data_security.py src/libs/portfolio-common/portfolio_common/source_data_products.py src/libs/portfolio-common/portfolio_common/enterprise_readiness.py src/services/query_service/app/enterprise_readiness.py src/services/query_service/app/settings.py src/services/query_control_plane_service/app/enterprise_readiness.py src/services/query_control_plane_service/app/settings.py src/services/ingestion_service/app/enterprise_readiness.py src/services/ingestion_service/app/main.py scripts/source_data_product_contract_guard.py tests/unit/libs/portfolio-common/test_source_data_security.py tests/unit/libs/portfolio-common/test_source_data_products.py tests/unit/libs/portfolio-common/test_enterprise_readiness_shared.py tests/unit/services/query_service/test_enterprise_readiness.py tests/unit/services/query_service/test_query_service_settings.py tests/unit/services/query_control_plane_service/test_control_plane_enterprise_readiness.py tests/unit/services/query_control_plane_service/test_control_plane_settings.py tests/unit/services/ingestion_service/test_enterprise_readiness.py tests/unit/scripts/test_source_data_product_contract_guard.py --ignore E501,I001`,
8. `python -m ruff format --check src/libs/portfolio-common/portfolio_common/source_data_security.py src/libs/portfolio-common/portfolio_common/source_data_products.py src/libs/portfolio-common/portfolio_common/enterprise_readiness.py src/services/query_service/app/enterprise_readiness.py src/services/query_service/app/settings.py src/services/query_control_plane_service/app/enterprise_readiness.py src/services/query_control_plane_service/app/settings.py src/services/ingestion_service/app/enterprise_readiness.py src/services/ingestion_service/app/main.py scripts/source_data_product_contract_guard.py tests/unit/libs/portfolio-common/test_source_data_security.py tests/unit/libs/portfolio-common/test_source_data_products.py tests/unit/libs/portfolio-common/test_enterprise_readiness_shared.py tests/unit/services/query_service/test_enterprise_readiness.py tests/unit/services/query_service/test_query_service_settings.py tests/unit/services/query_control_plane_service/test_control_plane_enterprise_readiness.py tests/unit/services/query_control_plane_service/test_control_plane_settings.py tests/unit/services/ingestion_service/test_enterprise_readiness.py tests/unit/scripts/test_source_data_product_contract_guard.py`,
9. `git diff --check`,
10. `make lint`.
