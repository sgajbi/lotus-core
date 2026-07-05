# CR-1359: Ingestion Ops JWT Claim Policy

Date: 2026-07-05

## Objective

Fix GitHub issue #588 by hardening privileged ingestion operations JWT authentication with required
claims, key identity, symmetric key rotation, and fail-closed non-local runtime configuration.

## Findings

The ingestion ops dependency accepted HS256 bearer JWTs through a custom verifier, but the policy
was under-specified: issuer and audience checks were optional, expiry and not-before were checked
only when present, `iat`, `jti`, principal identity, scope/capability, and `kid` were not required,
and non-local profiles could still rely on static token fallback without an explicit approval flag.

## Actions Taken

1. Added required JWT claims for `exp`, `iat`, `iss`, `aud`, `jti`, and one principal identity
   claim from `sub`, `client_id`, or `azp`.
2. Added required ops scope/capability validation through `scope`, `scp`, or `capabilities`.
3. Added `kid` support and active/previous HS256 key lookup for governed symmetric-key rotation.
4. Added bounded malformed-token, unsupported-algorithm, missing-claim, invalid time claim,
   expired-token, issuer, audience, scope, and key-id errors.
5. Added non-local strict settings validation for JWT issuer, audience, active key id, active
   secret, required scope, and explicit static-token fallback approval.

## Expected Improvement

Privileged ingestion operational routes now require source-owned identity, issuer, audience,
freshness, replay traceability, key identity, and route-family capability evidence before accepting
JWT bearer credentials. The change removes the prior optional-claim behavior and prevents
production-like deployments from silently depending on the local static ops token path.

## Compatibility

Local/dev/test profiles remain compatible with unset JWT material for developer startup. Non-local
or strict profiles now intentionally fail startup unless JWT auth is fully configured, and any
static ops-token fallback is explicitly approved through
`LOTUS_CORE_INGEST_OPS_STATIC_TOKEN_NON_LOCAL_APPROVED=true` with a non-default
`LOTUS_CORE_INGEST_OPS_TOKEN`.

No route path, request DTO, response DTO, OpenAPI schema, database schema, Kafka contract, metric
name, Dockerfile, or runtime topology changed.

## Validation Evidence

```powershell
python -m pytest tests\unit\services\ingestion_service\test_ops_controls.py tests\unit\services\ingestion_service\test_settings.py tests\integration\services\ingestion_service\test_ingestion_routers.py::test_ingestion_ops_supports_bearer_jwt -q
python -m ruff check src\services\ingestion_service\app\ops_controls.py src\services\ingestion_service\app\settings.py tests\unit\services\ingestion_service\test_ops_controls.py tests\unit\services\ingestion_service\test_settings.py tests\integration\services\ingestion_service\test_ingestion_routers.py
python -m ruff format --check src\services\ingestion_service\app\ops_controls.py src\services\ingestion_service\app\settings.py tests\unit\services\ingestion_service\test_ops_controls.py tests\unit\services\ingestion_service\test_settings.py tests\integration\services\ingestion_service\test_ingestion_routers.py
python scripts\architecture_documentation_catalog_guard.py
make quality-wiki-docs-gate
make security-control-coverage-guard
git diff --check
$env:PYTHONPATH = "src/services/ingestion_service;src/libs/portfolio-common"; python -c "import app.ops_controls; print('ingestion ops import ok')"
```

Results: 35 focused tests passed; scoped Ruff, format check, architecture catalog guard,
wiki/docs gate, security-control coverage guard, diff check, and ingestion ops import proof passed.
`git diff --check` reported only expected CRLF normalization warnings.

## Documentation Decision

Repo-local context, security docs, security wiki source, the RFC-0083 security target model, and
the codebase review ledger were updated because the privileged ingestion authentication contract
changed. No platform-wide skill change is required; the repeatable lesson is pinned in
repo-local context and tests.
