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
secure response headers, CORS, metrics access, auth/audit middleware, unauthenticated health and
metrics allowlist, payload limits, upload limits where relevant, secret/default validation, and
safe unhandled-error responses.

The guard proves static control installation. It does not prove live ingress policy, external IAM,
WAF behavior, penetration-test coverage, or environment-specific firewall rules.

Current runtime posture:

1. shared HTTP bootstrap adds `X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy`, and
   `Permissions-Policy` headers,
2. CORS is deny-by-default for browser cross-origin access unless
   `LOTUS_HTTP_CORS_ALLOW_ORIGINS` names allowed origins,
3. metrics remain internal-open by default and become bearer-token protected when
   `LOTUS_METRICS_ACCESS_TOKEN` is set,
4. business/operator HTTP apps install enterprise audit/authorization middleware; authz remains
   default-disabled for local compatibility until `ENTERPRISE_ENFORCE_AUTHZ` or
   `ENTERPRISE_ENFORCE_READ_AUTHZ` is enabled,
5. ingestion upload APIs reject payloads above `LOTUS_CORE_INGEST_UPLOAD_MAX_BYTES`.
