# CR-1249 Health Dependency Metrics

Date: 2026-07-01

## Objective

Fix GitHub issue #565 by adding low-cardinality metrics for shared readiness dependency checks.

## Change

- Added `health_dependency_check_total{service,dependency,status}`.
- Added `health_dependency_check_duration_seconds{service,dependency}`.
- Added `health_readiness_state{service,state}` with bounded `ready` and `not_ready` states.
- Routed shared readiness checks through the new metric helpers for `ok`, `unavailable`,
  `timeout`, and `error` outcomes.
- Passed stable service names into direct API health routers and standard health-only worker apps.

## Expected Improvement

Operators can trend dependency check latency and failure posture before `/health/ready` flips or
before intermittent database/Kafka degradation becomes a larger incident. The metric labels are
bounded to service, dependency, readiness status, and readiness state; raw exception text and
business identifiers stay in logs/support evidence, not Prometheus labels.

## Tests Added Or Updated

- Shared health tests prove fresh dependency checks emit service/dependency/status/duration metrics.
- Shared health tests prove cached readiness reuses dependency state without re-running dependency
  checks while still updating service readiness state.
- Shared monitoring tests prove the new health metrics use bounded label sets.
- Standard health-app bootstrap regression remains covered.

## Validation Evidence

- `python -m pytest tests\unit\libs\portfolio-common\test_health.py tests\unit\libs\portfolio-common\test_monitoring.py tests\unit\libs\portfolio-common\test_http_app_bootstrap.py::test_standard_health_app_exposes_shared_observability_contract tests\unit\libs\portfolio-common\test_worker_runtime.py -q --tb=short`
  -> 19 passed.
- `python -m pytest tests\integration\services\query_service\test_main_app.py tests\integration\services\ingestion_service\test_ingestion_main_app_contract.py -q --tb=short`
  -> 60 passed.
- `python -m ruff check <touched Python files>` -> passed.
- `python -m ruff format --check <touched Python files>` -> passed.
- `make typecheck` -> passed; no issues found in 50 source files.
- `make quality-wiki-docs-gate` -> passed.
- `git diff --check` -> passed.
- `powershell -ExecutionPolicy Bypass -File C:\Users\Sandeep\projects\lotus-platform\automation\Sync-RepoWikis.ps1 -CheckOnly -Repository lotus-core`
  -> expected unpublished wiki drift for changed `Operations-Runbook.md` plus existing
  `Outbox-Events.md`; publication remains post-merge.
- Stranded-truth reconciliation on 2026-07-01 found only active Dependabot branches:
  `origin/dependabot/github_actions/github-actions-02325a8da5` and
  `origin/dependabot/pip/python-runtime-b808a9fc65`. No CR-1249 durable truth was cherry-picked
  from those branches.

## Downstream Compatibility

No route paths, response bodies, health response schema, OpenAPI business contracts, database schema,
Kafka topics, or product APIs changed. This is an additive metrics contract change plus stable
service-label wiring for existing health routers.

## Documentation And Wiki Decision

Updated this architecture record, codebase review ledger, observability docs, operations runbook,
wiki source, repository context, quality scorecard, and refactor health report because the
operator-facing metrics contract changed. Wiki publication remains post-merge.

## Remaining Follow-Up

Producer-specific and downstream-client health checks should reuse the same metric helpers when
those checks become first-class readiness dependencies. Alert thresholds for dependency flapping
belong in the separate observability alert issue #501.
