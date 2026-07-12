# CR-1397 Observability Contract Test Pack

## Objective

Fix GitHub issue #571 by making Core observability contract evidence explicit, guarded, and tied to
the shared HTTP bootstrap, metrics, trace, structured-log, and source-safe diagnostics tests.

## Finding

Core already had meaningful observability tests and guards, including shared HTTP middleware
coverage across service apps, route-template metric tests, metric vocabulary validation, structured
log safety checks, source-safe payload evidence, and logging redaction tests. The evidence was
distributed, and malformed inbound `traceparent` behavior was not directly represented as a
regression. That made it easy to change middleware, diagnostics, or telemetry labels without
noticing which observability contract proof had to be refreshed.

## Actions

- Added `docs/standards/observability-contract-test-pack.v1.json` for #571 scenarios.
- Added `scripts/observability_contract_test_pack_guard.py` and focused guard tests.
- Wired `make observability-contract-test-pack-guard` into `make lint`.
- Added a shared HTTP bootstrap regression proving malformed `traceparent` headers are replaced
  with valid W3C trace context.
- Updated testing strategy, risk matrix, repository context, wiki source, and this ledger.

## Compatibility

No production runtime behavior, API route, DTO/OpenAPI schema, database schema, Kafka topic, event
payload, metric name, or deployment topology changed. The added behavior assertion documents the
existing middleware contract for invalid inbound trace context.

## Validation

Run before commit:

- `python -m pytest tests/unit/scripts/test_observability_contract_test_pack_guard.py tests/unit/libs/portfolio-common/test_http_app_bootstrap.py -k "observability_contract or malformed_traceparent" -q`
- `python -m pytest tests/unit/test_http_middleware_chain_contract.py tests/unit/libs/portfolio-common/test_http_app_bootstrap.py tests/unit/libs/portfolio-common/test_logging_utils.py tests/unit/libs/portfolio-common/test_monitoring.py tests/unit/scripts/test_metric_vocabulary_guard.py tests/unit/scripts/test_structured_log_guard.py tests/unit/services/ingestion_service/services/test_ingestion_payload_evidence.py tests/integration/services/ingestion_service/test_ingestion_routers.py -k "<observability evidence selection>" -q`
- `python scripts/observability_contract_test_pack_guard.py`
- `make observability-contract-test-pack-guard`
- `make test-ops-contract`
- scoped Ruff lint and format over the new guard/tests
- `make risk-based-test-coverage-matrix-guard`
- `make quality-wiki-docs-gate`
- `make lint`
- `git diff --check`

## Guidance Decision

Repo-local context changed because observability proof-pack maintenance is durable Core test truth.
No platform skill change is required for this slice; existing backend delivery and issue-loop
skills already require issue-derived patterns to become repo-native guards and context when
repeatable.
