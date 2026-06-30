# CR-1175 Worker Health Observability Bootstrap

## Objective

Begin GitHub issue #562 by applying the standard HTTP observability bootstrap to health-only worker
web apps.

## Expected Improvement

- Health-only worker web apps expose the same `/metrics`, `/health/live`, and `/health/ready`
  surface as API services.
- Health and metrics responses receive standard correlation, request, trace, and `traceparent`
  response headers.
- Worker health requests emit shared route-template HTTP metrics and standard request-completion
  logs.
- Worker OpenAPI documents `/metrics` with the same text/plain response normalization as API apps.

## Changes

- Added `create_standard_health_app(...)` to `portfolio_common.http_app_bootstrap` so health-only
  services use the same `configure_standard_http_app(...)` path as API services.
- Switched calculator, orchestration, aggregation, timeseries, valuation, and persistence worker
  `web.py` modules to the shared health-app factory with explicit service names, prefixes, and
  dependency checks.
- Added a worker-runtime guard that skips Prometheus instrumentation when the web app already
  exposes `/metrics`, avoiding duplicate runtime instrumentation after import-time bootstrap.
- Kept persistence custom Kafka processing metrics available by making `setup_metrics(...)`
  optionally return custom metrics without attaching a second Instrumentator.
- Added focused tests proving the shared health-app contract and duplicate-metrics guard.

## Compatibility

Existing health paths, readiness dependency checks, worker process managers, health probe ports, and
custom persistence consumer metrics are preserved. The intentional behavior change is additive
HTTP observability on worker health surfaces: standard headers, request logs, route-template HTTP
metrics, and normalized OpenAPI metadata now apply consistently.

## Validation

- `python -m pytest tests/unit/libs/portfolio-common/test_http_app_bootstrap.py tests/unit/libs/portfolio-common/test_worker_runtime.py -q`
- Worker health app HTTP smoke using `TestClient` for all nine touched `web.py` modules:
  `/health/live`, `/health/ready`, `/metrics`, and response header checks passed.
- `python -m ruff check src/libs/portfolio-common/portfolio_common/http_app_bootstrap.py src/libs/portfolio-common/portfolio_common/worker_runtime.py src/services/calculators/cashflow_calculator_service/app/web.py src/services/calculators/cost_calculator_service/app/web.py src/services/calculators/position_calculator/app/web.py src/services/calculators/position_valuation_calculator/app/web.py src/services/persistence_service/app/web.py src/services/persistence_service/app/consumer_manager.py src/services/persistence_service/app/monitoring.py src/services/pipeline_orchestrator_service/app/web.py src/services/portfolio_aggregation_service/app/web.py src/services/timeseries_generator_service/app/web.py src/services/valuation_orchestrator_service/app/web.py tests/unit/libs/portfolio-common/test_http_app_bootstrap.py tests/unit/libs/portfolio-common/test_worker_runtime.py`
- `python -m ruff format --check src/libs/portfolio-common/portfolio_common/http_app_bootstrap.py src/libs/portfolio-common/portfolio_common/worker_runtime.py src/services/calculators/cashflow_calculator_service/app/web.py src/services/calculators/cost_calculator_service/app/web.py src/services/calculators/position_calculator/app/web.py src/services/calculators/position_valuation_calculator/app/web.py src/services/persistence_service/app/web.py src/services/persistence_service/app/consumer_manager.py src/services/persistence_service/app/monitoring.py src/services/pipeline_orchestrator_service/app/web.py src/services/portfolio_aggregation_service/app/web.py src/services/timeseries_generator_service/app/web.py src/services/valuation_orchestrator_service/app/web.py tests/unit/libs/portfolio-common/test_http_app_bootstrap.py tests/unit/libs/portfolio-common/test_worker_runtime.py`

## Documentation And Wiki Decision

Updated this ledger entry, `docs/observability.md`, the quality scorecard/health report, and the
repo-local Operations Runbook wiki source. No product API or downstream business contract changed.

## Follow-Up

Issue #562 remains open pending PR, GitHub CI, and QA evidence. Broader follow-up should add an
automated inventory guard that rejects future runtime `web.py` modules that bypass the shared
bootstrap.
