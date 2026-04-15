# RFC-0083 Security, Tenancy, And Lifecycle Target Model

This document is the RFC-0083 Slice 9 target model for source-data product security, tenancy,
entitlement, audit, sensitivity, and retention posture in `lotus-core`.

It does not change runtime authorization behavior, persistence, DTOs, OpenAPI output, or downstream
contracts. It defines the governed profile that later runtime and contract slices must use.

The executable helper is:

1. `src/libs/portfolio-common/portfolio_common/source_data_security.py`
2. `tests/unit/libs/portfolio-common/test_source_data_security.py`

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

The helper validates that every product in the Slice 6 source-data product catalog has a profile.

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

## Validation

Slice 9 validation is:

1. `python -m pytest tests/unit/libs/portfolio-common/test_source_data_security.py -q`,
2. `python -m ruff check src/libs/portfolio-common/portfolio_common/source_data_security.py tests/unit/libs/portfolio-common/test_source_data_security.py --ignore E501,I001`,
3. `python -m ruff format --check src/libs/portfolio-common/portfolio_common/source_data_security.py tests/unit/libs/portfolio-common/test_source_data_security.py`,
4. `git diff --check`,
5. `make lint`.
