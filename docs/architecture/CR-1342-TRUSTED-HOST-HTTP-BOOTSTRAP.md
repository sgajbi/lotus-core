# CR-1342 Trusted Host HTTP Bootstrap

## Objective

Complete the GitHub issue #585 HTTP-bootstrap security slice by adding trusted-host enforcement to
the same shared FastAPI bootstrap that already owns secure headers, CORS, metrics access, lineage,
safe unhandled-error responses, and `/version` metadata.

## Finding

CR-1263 added secure response headers and deny-by-default CORS, but trusted-host validation was not
yet a shared control. That left production-like services dependent on ingress policy alone and made
new FastAPI apps easier to bootstrap without a host-header allowlist posture.

## Changes

- Added `configure_trusted_host_policy(...)` and `resolve_trusted_hosts(...)` to
  `portfolio_common.http_app_bootstrap`.
- Added `LOTUS_HTTP_TRUSTED_HOSTS` as the governed comma-separated trusted-host allowlist.
- Kept local/dev/test app-local compatibility by defaulting to `*` only outside the production
  security profile.
- Made production-like profiles fail closed when `LOTUS_HTTP_TRUSTED_HOSTS` is missing or contains
  `*`.
- Extended the security-control coverage contract and guard so future bootstrap drift is caught.
- Updated operations, security, wiki source, and repository context.

## Compatibility Impact

Local/dev/test behavior remains compatible. Production-like profiles now require explicit
non-wildcard trusted hosts before an app can complete shared HTTP bootstrap configuration. No
business route path, request DTO, response DTO, database schema, Kafka contract, metric name,
Dockerfile, image-release contract, or runtime topology changed.

## Validation Evidence

Focused validation before commit:

```powershell
python -m pytest tests/unit/libs/portfolio-common/test_http_app_bootstrap.py tests/unit/scripts/test_security_control_coverage_guard.py -q
python scripts/security_control_coverage_guard.py
python scripts/image_provenance_guard.py
```

The focused tests cover local wildcard compatibility, explicit host allowlists, rejected untrusted
hosts with secure response headers, production fail-closed missing-host behavior, and production
wildcard rejection.

## Documentation And Wiki

Updated repository docs and wiki source. Wiki publication remains a post-merge action through the
governed `Sync-RepoWikis.ps1 -Publish -Repository lotus-core` flow.
