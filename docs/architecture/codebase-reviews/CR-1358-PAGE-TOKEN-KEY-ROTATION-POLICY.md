# CR-1358: Page Token Key Rotation Policy

Date: 2026-07-05

## Objective

Fix GitHub issue #587 by hardening query-service cursor/page-token signing so non-local
deployments fail closed on default token secrets and new tokens carry versioned, keyed, expiring
envelopes with binding support.

## Findings

Query-service page tokens were HMAC signed but used a static local default secret outside a
governed policy boundary. The envelope stored only payload and signature, which prevented normal
key rotation, incident-response key rollover, expiry enforcement, and route or tenant binding.
The same pattern existed in the analytics page-token helper, so hardening only
`PageTokenCodec` would have left a parallel unversioned token path in place.

## Actions Taken

1. Added a versioned `PageTokenCodec` envelope with `v`, `kid`, `exp`, `iss`, `aud`, optional
   `route`, optional `tenant`, payload, and HMAC signature over the protected envelope fields.
2. Added active and previous key support for rotation windows.
3. Added expiry, issuer/audience, route, tenant, key-id, and signature validation.
4. Routed analytics page tokens through the shared codec instead of keeping a separate HMAC helper.
5. Added query-service settings for `LOTUS_CORE_PAGE_TOKEN_KEY_ID`,
   `LOTUS_CORE_PAGE_TOKEN_PREVIOUS_KEYS_JSON`, and `LOTUS_CORE_PAGE_TOKEN_TTL_SECONDS`.
6. Made non-local or strict profiles reject missing/default `LOTUS_CORE_PAGE_TOKEN_SECRET` and
   missing/default `LOTUS_CORE_PAGE_TOKEN_KEY_ID`.

## Expected Improvement

Cursor tokens are now operationally rotatable, bounded by expiry, and ready for route/tenant
binding where call sites provide that context. The old duplicated analytics token signer is gone,
so future page-token hardening has one implementation point.

## Compatibility

Local/dev/test profiles still allow the local development secret and key id. Non-local and strict
profiles now intentionally fail startup when page-token secret or key id are missing or still set
to local defaults. New tokens use a versioned envelope; blank token handling and decoded payload
shape remain unchanged for callers.

## Validation Evidence

```powershell
python -m pytest tests\unit\services\query_service\services\test_page_token_codec.py tests\unit\services\query_service\services\test_analytics_page_tokens.py tests\unit\services\query_service\test_query_service_settings.py -q
python -m pytest tests\unit\services\query_service\services\test_integration_service.py tests\unit\services\query_service\services\test_analytics_timeseries_service.py -q
python -m ruff check src\services\query_service\app\services\page_token_codec.py src\services\query_service\app\services\analytics_page_tokens.py src\services\query_service\app\services\analytics_timeseries_service.py src\services\query_service\app\services\integration_service.py src\services\query_service\app\settings.py tests\unit\services\query_service\services\test_page_token_codec.py tests\unit\services\query_service\services\test_analytics_page_tokens.py tests\unit\services\query_service\test_query_service_settings.py
python -m ruff format --check src\services\query_service\app\services\page_token_codec.py src\services\query_service\app\services\analytics_page_tokens.py src\services\query_service\app\services\analytics_timeseries_service.py src\services\query_service\app\services\integration_service.py src\services\query_service\app\settings.py tests\unit\services\query_service\services\test_page_token_codec.py tests\unit\services\query_service\services\test_analytics_page_tokens.py tests\unit\services\query_service\test_query_service_settings.py
make quality-wiki-docs-gate
git diff --check
$env:PYTHONPATH = "src/services/query_service;src/libs/portfolio-common"; python -c "import app.main; print('query app import ok')"
```

Results: 206 focused tests passed; scoped Ruff, format, wiki/docs gate, diff check, and query app
import proof passed. `git diff --check` reported only expected CRLF normalization warnings.

## Documentation Decision

Repo-local context, security docs, wiki source, and the codebase review ledger were updated because
the query-service runtime secret policy and token envelope contract changed. No platform-wide skill
change is required; this is now pinned by repo-local tests and context.
