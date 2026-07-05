# lotus-core Security

## Objective

`lotus-core` must protect portfolio, transaction, mandate, and operational data with secure
defaults suitable for private banking workloads.

## Baseline Requirements

1. Authentication and authorization boundaries are explicit.
2. Sensitive data is not logged.
3. Secrets come from governed configuration and are not committed.
4. CORS, headers, and API abuse protections are explicit.
5. Dependency and static security checks run in CI.
6. Source-data products carry entitlement, audit, sensitivity, and retention posture where governed.

## Gate Posture

`make quality-bandit-gate` is blocking for first-party Python security findings. Dependency audit
evidence remains part of the repo-native security posture through `make security-audit` and CI.
HTTP app control coverage is now enforced through `make security-control-coverage-guard`.

## HTTP Security Control Coverage

`lotus-core` now keeps FastAPI app security coverage in:

```powershell
contracts/security/security-control-coverage.v1.json
make security-control-coverage-guard
```

The contract lists every FastAPI app and its required control posture for standard HTTP bootstrap,
secure response headers, CORS, trusted-host enforcement, metrics access, auth/audit middleware,
unauthenticated health, metrics, OpenAPI/docs, and version allowlist, payload limits, upload limits
where relevant, secret/default validation, and safe unhandled-error responses.

The guard proves static control installation. It does not prove live ingress policy, external IAM,
WAF behavior, penetration-test coverage, or environment-specific firewall rules.

Current runtime posture:

1. shared HTTP bootstrap adds `X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy`, and
   `Permissions-Policy` headers,
2. CORS is deny-by-default for browser cross-origin access unless
   `LOTUS_HTTP_CORS_ALLOW_ORIGINS` names allowed origins,
3. trusted-host enforcement defaults to `*` for local/dev/test compatibility, while
   production-like profiles require non-wildcard `LOTUS_HTTP_TRUSTED_HOSTS`,
4. metrics remain internal-open by default and become bearer-token protected when
   `LOTUS_METRICS_ACCESS_TOKEN` is set,
5. business/operator HTTP apps install enterprise audit/authorization middleware; authz remains
   default-disabled for local compatibility until `ENTERPRISE_ENFORCE_AUTHZ` or
   `ENTERPRISE_ENFORCE_READ_AUTHZ` is enabled,
6. the shared enterprise middleware keeps `/health/live`, `/health/ready`, `/metrics`,
   `/openapi.json`, `/docs`, `/redoc`, and `/version` unauthenticated for operational access,
7. ingestion upload APIs reject payloads above `LOTUS_CORE_INGEST_UPLOAD_MAX_BYTES`,
8. ingestion write APIs have service-owned default capability rules instead of depending only on
   `ENTERPRISE_CAPABILITY_RULES_JSON`.
