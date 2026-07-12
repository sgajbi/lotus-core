# CR-1340 HTTP Middleware Chain Contract

## Scope

GitHub issue #606: shared FastAPI middleware-chain regression coverage across `lotus-core`
service app entrypoints.

## Objective

Prove that every standard FastAPI service app and worker health app uses the governed HTTP
middleware chain for runtime metadata, correlation, trace headers, secure response headers,
safe unhandled-exception responses, and route-template metrics. Fix any drift found by the matrix.

## Changes

1. Added `tests/test_support/http_middleware_contract.py` as a reusable app-level middleware
   contract helper.
2. Added `tests/unit/test_http_middleware_chain_contract.py` with a service-entrypoint matrix
   covering query, query-control-plane, ingestion, event replay, financial reconciliation, and all
   health-only worker web apps.
3. Fixed `portfolio_common.http_app_bootstrap` so unhandled route exceptions are converted inside
   the correlation middleware into the standard safe 500 response with correlation, request,
   trace, `traceparent`, and secure response headers.
4. Preserved outer HTTP observability for exception paths so route-template metrics record the 500
   status instead of losing the request when inner middleware raises.
5. Wired the new helper and matrix test into the existing HTTP bootstrap Ruff lint/format slice in
   `make lint`.

## Behavior And Compatibility

Existing route paths, request DTOs, response DTOs, OpenAPI schemas, database schema, Kafka
contracts, metrics names, and runtime topology are unchanged.

The intentional behavior improvement is limited to unhandled exception paths: standard apps now
return the same safe JSON body with the same `correlation_id` payload as before, plus the governed
lineage and secure response headers, and the existing HTTP request metrics record the 500 response
with the route template.

## Validation Evidence

Focused local validation:

1. `python -m pytest tests/unit/test_http_middleware_chain_contract.py tests/unit/libs/portfolio-common/test_http_app_bootstrap.py -q`
2. `python -m ruff check src/libs/portfolio-common/portfolio_common/http_app_bootstrap.py tests/test_support/http_middleware_contract.py tests/unit/test_http_middleware_chain_contract.py --ignore E501,I001`
3. `python -m ruff format --check src/libs/portfolio-common/portfolio_common/http_app_bootstrap.py tests/test_support/http_middleware_contract.py tests/unit/test_http_middleware_chain_contract.py`

## Documentation, Wiki, Context, And Skill Decision

Updated repo-local context because standard HTTP exception, lineage, and metric behavior changed.

No wiki source update is required: the operator-facing contract remains the same safe exception
response and standard lineage posture, now enforced consistently across app entrypoints.

No platform skill source change is required. The durable lesson is enforced through the shared
test helper and service-entrypoint matrix rather than additional prose.

## Remaining Work

Broader issue families for trusted host policy, request-size protection, enterprise authorization,
and audit middleware remain governed by their own security/operability issues. This slice fixes
the cross-app standard bootstrap matrix for #606 pending PR CI/QA and issue closure.
