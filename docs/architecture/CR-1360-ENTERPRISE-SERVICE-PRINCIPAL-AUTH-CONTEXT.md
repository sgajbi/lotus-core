# CR-1360: Enterprise Service Principal Auth Context

Date: 2026-07-05

## Objective

Fix GitHub issue #583 by replacing header-asserted enterprise capabilities with a verifiable
service-principal auth-context contract in the shared enterprise-readiness middleware.

## Findings

Enterprise authorization trusted `X-Service-Identity` and `X-Capabilities` as caller-supplied
headers. `Authorization` was accepted as a service-identity presence marker without parsing or
validation. That meant a direct caller could forge a service identity and capability list when
enterprise authorization was enabled.

## Actions Taken

1. Added a signed enterprise auth-context contract using `X-Enterprise-Auth-Key-Id`,
   `X-Enterprise-Auth-Timestamp`, and `X-Enterprise-Auth-Signature`.
2. Bound the signature to service identity, actor, tenant, role, correlation id, timestamp, key id,
   and normalized capability claims.
3. Added auth-context freshness validation through `ENTERPRISE_AUTH_CONTEXT_MAX_AGE_SECONDS`.
4. Added `ENTERPRISE_AUTH_CONTEXT_HMAC_SECRET` to default, query-service, and query-control-plane
   enterprise settings.
5. Rejected unsupported `Authorization` bearer values as unverified principals instead of treating
   header presence as service identity.
6. Updated query, query-control-plane, ingestion, and shared tests to use signed service-principal
   capabilities and added forged capability/service-identity regressions.

## Expected Improvement

Capability enforcement is now tied to a verified internal auth context rather than arbitrary
request headers. A trusted gateway or mTLS sidecar can inject the signed context at the protected
boundary, and service-local authorization logic consumes the verified capability set.

## Compatibility

Enterprise authorization disabled local paths remain unchanged. When write or read authorization is
enabled, callers must provide the signed auth context. Production-like runtime validation now
reports `missing_auth_context_secret` when authz is enabled without
`ENTERPRISE_AUTH_CONTEXT_HMAC_SECRET`.

No route path, request DTO, response DTO, OpenAPI schema, database schema, Kafka contract, metric
name, Dockerfile, or runtime topology changed.

## Validation Evidence

```powershell
python -m pytest tests\unit\libs\portfolio-common\test_enterprise_readiness_shared.py tests\unit\services\query_service\test_enterprise_readiness.py tests\unit\services\query_service\test_query_service_settings.py tests\unit\services\query_control_plane_service\test_control_plane_enterprise_readiness.py tests\unit\services\query_control_plane_service\test_control_plane_settings.py tests\unit\services\ingestion_service\test_enterprise_readiness.py tests\integration\services\ingestion_service\test_ingestion_main_app_contract.py::test_enterprise_middleware_denies_ingestion_write_missing_capability -q
python -m ruff check src\libs\portfolio-common\portfolio_common\enterprise_readiness.py src\services\query_service\app\settings.py src\services\query_control_plane_service\app\settings.py tests\unit\libs\portfolio-common\test_enterprise_readiness_shared.py tests\unit\services\query_service\test_enterprise_readiness.py tests\unit\services\query_service\test_query_service_settings.py tests\unit\services\query_control_plane_service\test_control_plane_enterprise_readiness.py tests\unit\services\query_control_plane_service\test_control_plane_settings.py tests\unit\services\ingestion_service\test_enterprise_readiness.py tests\integration\services\ingestion_service\test_ingestion_main_app_contract.py
python -m ruff format --check src\libs\portfolio-common\portfolio_common\enterprise_readiness.py src\services\query_service\app\settings.py src\services\query_control_plane_service\app\settings.py tests\unit\libs\portfolio-common\test_enterprise_readiness_shared.py tests\unit\services\query_service\test_enterprise_readiness.py tests\unit\services\query_service\test_query_service_settings.py tests\unit\services\query_control_plane_service\test_control_plane_enterprise_readiness.py tests\unit\services\query_control_plane_service\test_control_plane_settings.py tests\unit\services\ingestion_service\test_enterprise_readiness.py tests\integration\services\ingestion_service\test_ingestion_main_app_contract.py
make quality-wiki-docs-gate
make security-control-coverage-guard
$env:PYTHONPATH = "src/services/query_service;src/libs/portfolio-common"; python -c "import app.main; print('query app import ok')"
$env:PYTHONPATH = "src/services/query_control_plane_service;src/libs/portfolio-common"; python -c "import app.main; print('query control plane app import ok')"
$env:PYTHONPATH = "src/services/ingestion_service;src/libs/portfolio-common"; python -c "import app.main; print('ingestion app import ok')"
git diff --check
```

Results: 96 focused tests passed; scoped Ruff, format check, wiki/docs gate, security-control
coverage guard, query app import proof, query-control-plane app import proof, and ingestion app
import proof passed. `git diff --check` passed with expected CRLF normalization warnings only.

## Documentation Decision

Repo-local context, security docs, security wiki source, the RFC-0083 security target model, and
the codebase review ledger were updated because the enterprise service-to-service trust contract
changed. No platform-wide skill change is required; the repeatable lesson is pinned in repo-local
context and tests.
