# CR-1265 Production Read Authorization And Audit Profile

## Objective

Fix GitHub issue #442 by making `lotus-core` service-local enterprise authorization, read
authorization, read auditing, capability-rule, and runtime-configuration enforcement default to a
fail-closed production profile for production-like environments while preserving local/dev/test
compatibility.

## Expected Improvement

This slice turns repeated opt-in security defaults into one reusable platform pattern:

1. `portfolio_common.runtime_settings.production_security_profile_enabled(...)` is the single
   environment/profile decision point,
2. production-like `ENVIRONMENT` values `prod`, `production`, `preprod`, `pre-prod`,
   `pre-production`, `staging`, `stage`, and `uat` enable the production security profile by
   default,
3. `LOTUS_CORE_PRODUCTION_SECURITY_PROFILE=false` remains an explicit, auditable opt-out for
   non-production drills or transitional environments,
4. `query_service`, `query_control_plane_service`, and shared default enterprise readiness settings
   now inherit the same production defaults,
5. the shared runtime now reads `ENTERPRISE_ENFORCE_RUNTIME_CONFIG` through typed settings, so
   production profile validation fails closed instead of depending on raw environment fallback.

## Downstream Compatibility

No route path, OpenAPI response shape, source-data product contract, database schema, Kafka topic,
or downstream DTO changed. Local/dev/test defaults remain opt-in. The intentional behavior change is
runtime configuration only: production-like environments now default to enforcing enterprise write
authorization, read authorization, read auditing, capability-rule checks, and runtime-config
validation unless the deployment explicitly overrides the profile.

This is service-local posture hardening. It does not claim full gateway, ingress, IAM, WAF,
network, or penetration-test closure. Those remain higher-lane platform/runtime proofs.

## Validation Evidence

- `python -m pytest tests\unit\libs\portfolio-common\test_runtime_settings.py tests\unit\libs\portfolio-common\test_enterprise_readiness_shared.py tests\unit\services\query_service\test_query_service_settings.py tests\unit\services\query_control_plane_service\test_control_plane_settings.py tests\unit\services\query_service\test_enterprise_readiness.py tests\unit\services\query_control_plane_service\test_control_plane_enterprise_readiness.py -q`:
  88 passed.
- `python -m ruff format ...`: reformatted the eight touched Python files.
- `python -m ruff check ... --ignore E501,I001`: passed for the touched runtime/settings/tests.
- `make security-control-coverage-guard`: passed.
- `make quality-wiki-docs-gate`: passed.
- `make typecheck`: passed with no issues in 50 source files.
- `make lint`: passed, including Ruff, format checks, monetary-float guard, ingestion contract
  guards, config-access guard, metric-vocabulary guard, repository-output-shape guard,
  security-control coverage guard, structured-log guard, QCP problem-details guard,
  temporal-vocabulary guard, route-family guard, source-data product guard, analytics-input
  consumer guard, event-runtime guard, and RFC-0083 closure guard.
- `make security-audit`: passed with no known vulnerabilities; local editable service packages were
  skipped by `pip-audit` because they are not PyPI packages.
- `git diff --check`: passed with expected CRLF normalization warnings on touched Markdown files.
- `powershell -ExecutionPolicy Bypass -File ..\lotus-platform\automation\Sync-RepoWikis.ps1 -CheckOnly -Repository lotus-core`:
  failed because the published GitHub wiki is not synchronized with repo-authored wiki source.
  Drift reported on `Data-Models.md`, `Mesh-Data-Products.md`, `Operations-Runbook.md`,
  `Outbox-Events.md`, `Overview.md`, `Security-and-Governance.md`, `Supported-Features.md`, and
  `Validation-and-CI.md`. The first four remain pre-existing publication drift; the remaining pages
  include intentional branch wiki-source changes that need normal post-merge publication from
  `main`.

## Documentation And Wiki Decision

Updated RFC-0083 security and production-readiness truth, README current-state truth,
repo-engineering context, quality scorecard, refactor health report, codebase review ledger, and
repo-authored wiki source. Wiki publication remains pending until this branch is merged and the
governed repository wiki sync step runs from `main`.
