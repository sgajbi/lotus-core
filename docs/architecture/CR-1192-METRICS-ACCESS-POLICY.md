# CR-1192 Metrics Access Policy

Date: 2026-06-30

## Objective

Fix GitHub issue #678 by making the shared `/metrics` exposure policy explicit, testable, and
configurable without breaking private Prometheus scrape compatibility.

## Change

- Added a shared `MetricsAccessPolicy` to the standard HTTP bootstrap.
- Moved `LOTUS_METRICS_ACCESS_TOKEN` parsing into the approved common metrics settings layer so
  shared HTTP middleware does not read environment variables directly.
- Preserved default `internal_open` mode for private scrape-network compatibility.
- Added bearer-token protection when `LOTUS_METRICS_ACCESS_TOKEN` or the bootstrap
  `metrics_access_token` parameter is configured.
- Added shared `/metrics` middleware that denies unauthorized scrapes with
  `METRICS_ACCESS_DENIED` and allows authorized bearer-token scrapes.
- Routed web-backed worker runtime `/metrics` exposure through the same access policy, including
  worker apps that already registered a metrics route before startup instrumentation.
- Updated standard OpenAPI enrichment so `/metrics` is described as an operational scrape endpoint,
  not a public business API, with `text/plain` success content and a documented `403` access-policy
  response.
- Updated the observability documentation with the metrics trust-boundary contract.

## Expected Improvement

`/metrics` no longer relies on implicit anonymous exposure as the only tested contract. Services that
use the shared HTTP bootstrap, standard health app, or web-backed worker runtime now share the same
metrics policy and can protect scrapes through configuration when the endpoint may be reachable
outside a private metrics network.

## Tests Added

- Default metrics policy resolves to `internal_open`.
- `LOTUS_METRICS_ACCESS_TOKEN` resolves to bearer-token protected mode.
- Unauthorized `/metrics` requests are denied when a metrics token is configured.
- Authorized bearer-token scrapes still return Prometheus metrics.
- Web-backed worker runtime `/metrics` denies unauthorized scrapes and allows authorized scrapes
  when a metrics token is configured.
- Worker apps with an existing `/metrics` route still receive the shared token policy.
- OpenAPI documents `/metrics` as an operational scrape endpoint with text/plain success and access
  denial examples.
- The configuration access guard permits metrics-token env reads only in the approved common
  metrics settings module and passes for the source tree.
- Existing query-service and ingestion-service metrics tests continue proving default internal
  scrape compatibility.

## Validation Evidence

- `python -m pytest tests/unit/libs/portfolio-common/test_http_app_bootstrap.py tests/integration/services/query_service/test_main_app.py::test_openapi_declares_metrics_as_text_plain tests/integration/services/query_service/test_main_app.py::test_metrics_include_http_series_samples tests/integration/services/ingestion_service/test_ingestion_main_app_contract.py::test_openapi_declares_metrics_as_text_plain tests/integration/services/ingestion_service/test_ingestion_main_app_contract.py::test_metrics_include_http_series_samples -q`
  passed with 14 tests.
- `python -m pytest tests/unit/libs/portfolio-common/test_http_app_bootstrap.py tests/unit/libs/portfolio-common/test_worker_runtime.py tests/unit/scripts/test_source_contract_guards.py -q`
  passed with 19 tests.
- `python scripts/config_access_guard.py` passed.
- `python -m ruff check src/libs/portfolio-common/portfolio_common/http_app_bootstrap.py src/libs/portfolio-common/portfolio_common/openapi_enrichment.py tests/unit/libs/portfolio-common/test_http_app_bootstrap.py`
  passed.
- `python -m ruff format --check src/libs/portfolio-common/portfolio_common/http_app_bootstrap.py src/libs/portfolio-common/portfolio_common/openapi_enrichment.py tests/unit/libs/portfolio-common/test_http_app_bootstrap.py`
  passed.
- `git diff --check` passed.

## Downstream Compatibility

Default local and private-network scrape behavior is preserved: `/metrics` still returns `200` when
no metrics token is configured. The intentional behavior change is opt-in: when
`LOTUS_METRICS_ACCESS_TOKEN` is configured, `/metrics` requires `Authorization: Bearer <token>` and
returns `403 METRICS_ACCESS_DENIED` otherwise. No business API route, database schema, metric name,
metric label, or success payload shape changed.

## Documentation And Wiki Decision

This architecture record, `docs/observability.md`, the codebase review ledger, and quality/refactor
scorecards were updated. No repo-local wiki update is required because no wiki-authored operator
runbook currently describes metrics ingress configuration.

## Remaining Follow-Up

- Add ingress/platform-stack validation that public ingress does not route `/metrics` unless an
  explicit operational policy allows it.
- Consider a future inventory guard that rejects newly introduced service apps exposing metrics
  outside the shared bootstrap, standard health app, or worker-runtime policy path.
- Coordinate production deployment secret naming and rotation guidance with platform operations.
