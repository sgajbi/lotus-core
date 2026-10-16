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

Dependency license and supportability evidence is lock-owned. Use
`make dependency-technology-inventory` for the report-only exact-SHA receipt and
`make dependency-technology-certify` when an allowed verdict is mandatory. The inventory never
uses ambient packages or popularity as approval evidence. It currently blocks certification for
explicitly listed missing, compound, or ambiguous license evidence and for dependencies without
governed upstream support, vulnerability-disclosure, and lifecycle authorities. PyPI release
existence never certifies supportability. This is a truthful control result, not permission to waive
the component.

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
7. ingestion upload APIs reject payloads above `LOTUS_CORE_INGEST_UPLOAD_MAX_BYTES` and parser
   work above configured row, column, and cell-length budgets,
8. ingestion write APIs have service-owned default capability rules instead of depending only on
   `ENTERPRISE_CAPABILITY_RULES_JSON`,
9. enterprise capability checks consume a signed service-principal auth context rather than trusting
   arbitrary `X-Capabilities` or `X-Service-Identity` headers,
10. bulk upload preview returns no sample rows by default; privileged sample rows require signed
   `ingestion.uploads.preview_samples.read` and field redaction,
11. privileged ingestion ops JWTs require issuer, audience, expiry, issued-at, replay id, principal
   identity, required ops scope/capability, `kid`, and active/previous-key validation,
12. non-local ingestion profiles cannot use static ops-token fallback unless
   `LOTUS_CORE_INGEST_OPS_STATIC_TOKEN_NON_LOCAL_APPROVED=true` and a non-default token are set,
13. query-service page tokens use versioned, keyed, expiring envelopes and non-local profiles fail
   closed unless `LOTUS_CORE_PAGE_TOKEN_SECRET` and `LOTUS_CORE_PAGE_TOKEN_KEY_ID` are non-default.
14. persistence-consumer schema and JSON rejection logs exclude raw input and exception traceback;
    they retain only bounded schema locations/types/counts, stable reason code and correlation
    identity, while the shared formatter redacts quoted, non-string, escaped, multiline and
    truncated values under complete compound, punctuated or JSON-escaped sensitive mapping keys as
    a bounded-pass backstop across four nested serialization layers without erasing non-sensitive
    compound diagnostics. Malformed broker payload evidence scans at most 16,384 retained
    characters, carries an explicit truncation marker, and is reused for the 1,500-character
    durable excerpt.

## Enterprise Service Context HMAC v1

This section defines the existing producer-owned byte protocol
`lotus-enterprise-auth-context-v1`. Its implementation is
[`_enterprise_auth_context_signature`](../../src/libs/portfolio-common/portfolio_common/enterprise_readiness.py),
with that module's `_normalize_headers`, `_capabilities_from_headers` and
`verify_service_principal`. The
[shared known-answer tests](../../tests/unit/libs/portfolio-common/test_enterprise_readiness_shared.py)
pin compatibility independently of the signer. Context authentication and native product
authorization remain separate boundaries.

### Canonical Bytes

1. Lowercase supplied header names with Python `str.lower()`; do not strip names.
   Strip values with `str.strip()`. Do not case-fold values or normalize Unicode.
   The dictionary helper does not provide duplicate HTTP-header admission: producers must construct
   each authority header once and refuse caller overrides.
2. Split normalized `X-Capabilities` on comma, strip tokens, discard empty tokens, deduplicate
   case-sensitively, sort with Python's case-sensitive lexical ordering, and join with comma.
   Equivalent order, duplicate tokens and surrounding whitespace retain the signature.
3. Join these nine single-line strings with literal LF (`0x0a`), with no trailing LF:

   ```text
   lotus-enterprise-auth-context-v1
   <X-Enterprise-Auth-Key-Id>
   <X-Service-Identity>
   <X-Actor-Id>
   <X-Tenant-Id>
   <X-Role>
   <X-Correlation-Id>
   <X-Enterprise-Auth-Timestamp>
   <sorted unique comma-joined capabilities>
   ```

4. Encode the canonical string and effective secret as UTF-8. Compute HMAC-SHA256 and emit its
   lowercase 64-character hexadecimal digest in `X-Enterprise-Auth-Signature`.
   Core uses `hmac.compare_digest`; uppercase hexadecimal is not equivalent.

The signer assumes normalized input and does not strip its secret. The verifier strips
`ENTERPRISE_AUTH_CONTEXT_HMAC_SECRET` before computing its expected signature. Producers must use
that effective secret, provision clean key material, and keep it out of headers, bodies, URLs,
logs and evidence. The public synthetic literals below are test data, never deployment credentials.

### Key Selection, Lifetime And Refusal

Core has one configured effective secret. When `ENTERPRISE_PRIMARY_KEY_ID` is nonblank, the
normalized incoming key ID must equal that configured string exactly. A blank configured ID
disables that match; producers and deployment owners should require an explicit clean nonblank ID.
This protocol has no per-key secret discovery, previous-key set or revocation lookup.
Provisioning, trust, rotation and withdrawal belong to the deployment/IAM owner.

Core parses the normalized timestamp with Python `int()` and compares
`abs(int(time.time()) - timestamp)` with `ENTERPRISE_AUTH_CONTEXT_MAX_AGE_SECONDS`
(default 300, minimum 1). At the default, both past and future offsets of exactly 300 seconds
pass freshness; 301 seconds refuse. Original normalized timestamp spelling is signed:
`+1792080000` and `1792080000` parse equally but have different signatures.
Producers should emit fresh canonical decimal seconds for each request.

Missing effective secret, service identity, valid timestamp or signature refuses verification;
wrong key ID, stale timestamp, changed signed fields or invalid signature also refuse.
Nonempty normalized `Authorization` refuses this verifier. Producers must omit `Authorization`;
neither the HMAC secret nor any monthly-proof signing key is a bearer token.
Service, actor, tenant, role and correlation fields are bounded to 128 characters.
Enabled authorization additionally requires nonblank actor, tenant, role and correlation;
`verify_service_principal` alone does not establish complete request admission.

### Independent Known Answers

The public synthetic key is `public-synthetic-manage-core-hmac-v1-key`.
Both vectors use key ID `synthetic-core-key-v1`, service `lotus-manage`,
tenant `synthetic-tenant`, role `system`, timestamp `1792080000`, and input capabilities
`source_data.portfolio_historical_registry.read,source_data.portfolio_financial_source_cut.read`.
The final canonical capability line is
`source_data.portfolio_financial_source_cut.read,source_data.portfolio_historical_registry.read`.

| Vector | Actor | Correlation | Expected lowercase HMAC-SHA256 |
| --- | --- | --- | --- |
| ASCII | `synthetic-manage-reader` | `synthetic-correlation-001` | `509f603c9e00d7db7939488c58155c31814373f3426c79c8d3242041c58d1228` |
| UTF-8 primitive | `synthetic-café` | `synthetic-correlation-Ω` | `dc26eb3f661088a6c46227c2135fd175fb739686ac5fbb0efd511c76915f7290` |

The Unicode answer pins UTF-8 primitive behavior without Unicode normalization. It does not
establish Unicode HTTP-header transport support. Manage's consumer adapter restricts its HTTP
policy to ASCII and refuses Unicode policy values before dispatch.

### Native Read Authority And Limits

For `PortfolioHistoricalRegistry` and `PortfolioFinancialSourceCut`, a valid signature does not
replace independently verified tenant context, matching service identity, catalog consumer
membership, exact product capability, server-owned read grant, or enabled tenant feature policy.
The current supported consumer for both products is `lotus-manage`.

| Native POST read | Required capability | Feature flag |
| --- | --- | --- |
| `/integration/portfolio-historical-registries/query` | `source_data.portfolio_historical_registry.read` | `LOTUS_CORE_CAP_HISTORICAL_REGISTRY_READ_ENABLED` |
| `/integration/financial-source-cuts/query` | `source_data.portfolio_financial_source_cut.read` | `LOTUS_CORE_CAP_FINANCIAL_SOURCE_CUT_READ_ENABLED` |

Both flags default to false; tenant-specific policy still applies.
`PORTFOLIO_NEUTRAL_SOURCE_READ_GRANTS_JSON` defaults to `[]` and independently matches exact
service, tenant, source system, registry scope and product. Producer write grants do not confer
consumer read grants. These source read grants do not establish portfolio-level bank entitlement.

The signature binds context fields only, without HTTP method, origin, route, query, body, cursor,
response bytes or response roots. Consumers must retain exact-target, no-redirect and caller-header
admission controls alongside body/cut/tenant validation. Timestamp freshness and signed correlation
do not make context single-use: identical context can pass again within its freshness window.
There is no nonce ledger here.

Shared-key possession does not establish bank/user IAM, supplier enrollment or source authority,
qualified financial inputs, complete population, institutional monthly approval, or official
activation. Separate Manage A/C clients do not prove separately enrolled cryptographic principals.
Monthly proof verification and Performance acceptance remain independently owned controls.
