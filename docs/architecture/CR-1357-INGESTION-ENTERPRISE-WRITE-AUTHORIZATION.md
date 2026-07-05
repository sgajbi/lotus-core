# CR-1357: Ingestion Enterprise Write Authorization

Date: 2026-07-05

## Objective

Fix GitHub issue #582 by making `ingestion_service` use the shared enterprise-readiness
authorization and audit middleware with source-owned default capability rules for canonical write
routes.

## Findings

The security-control contract classified `ingestion_service` as an enterprise-middleware business
API, but the service did not own default write capability rules for its write plane. Enforced
authorization could validate enterprise headers, but strict capability-rule mode still depended on
hand-written environment JSON for ingestion routes. Health, metrics, OpenAPI, docs, ReDoc, and
version paths also needed an explicit shared unauthenticated allowlist so enabling read
authorization does not break operational probes.

## Actions Taken

1. Added a service-local `ingestion_service.app.enterprise_readiness` wrapper over
   `portfolio_common.enterprise_readiness`.
2. Added default capability rules for portfolio, transaction, instrument, market-price, FX,
   business-date, portfolio-bundle, upload, reprocessing, and reference-data ingestion write
   routes.
3. Extended the shared runtime to merge service-owned default capability rules before optional
   environment overrides.
4. Added an explicit shared unauthenticated operational-path allowlist for health, metrics,
   OpenAPI, docs, ReDoc, and version endpoints.
5. Wired `ingestion_service` through the service-local enterprise middleware while preserving the
   existing ingestion write-payload budget resolver.

## Expected Improvement

Ingestion source-of-truth mutations now have a deterministic service-owned capability policy,
source-safe denied-write audit evidence, and a failing route-coverage test if future ingestion
write routes are added without capability rules.

## Compatibility

Local/dev/test compatibility is preserved because enterprise write authorization remains opt-in
outside production-like profiles. Existing route paths, request DTOs, response DTOs, OpenAPI
schemas, Kafka topics, database schemas, rate-limit behavior, upload byte-budget behavior, and
runtime topology are unchanged. In production-like or explicitly enforced environments, ingestion
write requests now intentionally require actor, tenant, role, correlation id, service identity, and
the route-specific write capability.

## Validation Evidence

```powershell
python -m pytest tests\unit\libs\portfolio-common\test_enterprise_readiness_shared.py tests\unit\services\ingestion_service\test_enterprise_readiness.py tests\integration\services\ingestion_service\test_ingestion_main_app_contract.py tests\unit\scripts\test_security_control_coverage_guard.py -q
python -m ruff check src\libs\portfolio-common\portfolio_common\enterprise_readiness.py src\services\ingestion_service\app\enterprise_readiness.py src\services\ingestion_service\app\main.py scripts\security_control_coverage_guard.py tests\unit\libs\portfolio-common\test_enterprise_readiness_shared.py tests\unit\services\ingestion_service\test_enterprise_readiness.py tests\integration\services\ingestion_service\test_ingestion_main_app_contract.py tests\unit\scripts\test_security_control_coverage_guard.py
python -m ruff format --check src\libs\portfolio-common\portfolio_common\enterprise_readiness.py src\services\ingestion_service\app\enterprise_readiness.py src\services\ingestion_service\app\main.py scripts\security_control_coverage_guard.py tests\unit\libs\portfolio-common\test_enterprise_readiness_shared.py tests\unit\services\ingestion_service\test_enterprise_readiness.py tests\integration\services\ingestion_service\test_ingestion_main_app_contract.py tests\unit\scripts\test_security_control_coverage_guard.py
make security-control-coverage-guard
python scripts\architecture_documentation_catalog_guard.py
make quality-wiki-docs-gate
git diff --check
$env:PYTHONPATH = "src/services/ingestion_service;src/libs/portfolio-common"; python -c "import app.main; print('ingestion app import ok')"
```

Results: 74 focused tests passed; scoped Ruff, format, security-control coverage, architecture
documentation, wiki/docs, diff check, and ingestion app import proof passed. `git diff --check`
reported only expected CRLF normalization warnings.

## Documentation Decision

Repo-local context, the RFC-0083 security target model, the Security and Governance wiki source,
and this codebase review ledger were updated because the service-local enterprise authorization
policy changed. No platform-wide skill change is required for this slice; the repeatable issue
workflow requirement is already covered by the GitHub issue fix skill and repo-specific recurrence
is now pinned by tests and repository context.
