# lotus-core Security

## Objective

`lotus-core` must protect portfolio, transaction, mandate, and operational data with secure
defaults suitable for private banking workloads.

## Baseline Requirements

1. Authentication and authorization boundaries are explicit.
2. Sensitive data is not logged.
3. Secrets come from governed configuration and are not committed.
4. CORS, headers, and API abuse protections are explicit.
5. Dependency and static security checks run in CI.
6. Source-data products carry entitlement, audit, sensitivity, and retention posture where governed.

## Initial Gate Posture

The report-only quality workflow adds `bandit` and `pip-audit` publication steps. These are
baseline/report-only first and should later ratchet to regression and enterprise-readiness gates.
