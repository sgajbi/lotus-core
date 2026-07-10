# CR-1462: Target Worker Security Coverage

Date: 2026-07-10
Issue: #468 active-review feedback
Status: Hardened locally

## Objective

Bring the combined transaction-processing health app into the repository's explicit security
control inventory before image or runtime cutover.

## Decision

`portfolio_transaction_processing_service_web` is a health-only worker API. It has no business
routes, request payloads, or uploads. It uses the shared standard health bootstrap and exposes only
the governed operational/documentation allowlist:

- `/docs`;
- `/health/live`;
- `/health/ready`;
- `/metrics`;
- `/openapi.json`;
- `/redoc`;
- `/version`.

The contract therefore records `health_only_no_business_routes`,
`not_applicable_health_only` payload limits, and no upload limit. Metrics remain subject to the
shared internal-open or bearer-token access policy; this entry does not claim public-ingress safety.

## Evidence And Compatibility

- target health/security contract plus guard tests: 7 passed;
- `security_control_coverage_guard.py`: passed;
- scoped Ruff lint/format and diff checks: passed.

No API payload, Kafka contract, database schema, processing behavior, auth default, or deployment
topology changed. No README/wiki update is required because the target remains undeployed.
