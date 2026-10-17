# Neutral Source Custody Operations

This runbook describes the implemented source custody path and its validation boundary.
Native PostgreSQL, deployed source-off replay, target scale and downstream financial/operator
acceptance require separately admitted evidence. A completed custody job is not bank approval.

## Runtime And Admission

The existing ingestion service atomically stages immutable chunks/manifests with native
`IngestionJob` receipts. Supervised workers run inside the existing persistence process;
no additional service or deployment is introduced. The existing outbox dispatcher emits a
reference-only `PortfolioFinancialSourceCutCompleted` fact after terminal custody commits.
The topic is producer-only: `portfolio.financial_source_cuts.completed`, 12 partitions,
no active runtime consumer group. Consumers request authoritative retained evidence through QCP.

Four POST write collections accept opaque identities in the closed body:

- `/ingest/portfolio-historical-registry-chunks`
- `/ingest/portfolio-historical-registry-cuts`
- `/ingest/portfolio-financial-source-cut-chunks`
- `/ingest/portfolio-financial-source-cuts`

`X-Idempotency-Key`, verified tenant/service identity and an exact source grant are required.
Producer service identity must match the declared source system. The typed JSON configuration
`LOTUS_PORTFOLIO_REGISTRY_SOURCE_GRANTS_JSON` defaults empty and admits only explicit
`tenant_id`, `source_system`, `registry_scope_id` and supported `products`. Existing four-field
fact grants are unchanged. Required capabilities are
`ingestion.portfolio_historical_registries.write` and
`ingestion.portfolio_financial_source_cuts.write`.

Actual streamed uncompressed request bytes are bounded before typed parsing, including requests
without a trustworthy Content-Length. Non-identity content encoding is refused. Chunks precede
their seal. Exact typed-and-raw replay returns the first native receipt; different raw bytes
remain divergent even when they describe the same typed content. A 202 acknowledgement identifies
the original job and does not claim completion. Poll that job using the existing ingestion job API.

## Opt-In App-Local Authentication Transport

The base `docker-compose.yml` does not enroll an auth-context key. The optional
`docker-compose.source-custody.yml` forwards an existing operator-owned key and exact grants
only to ingestion and query control plane. It enables existing write authorization in ingestion
and write/read authorization in QCP so middleware verifies each affected request and propagates
its verified tenant/service context to source admission. It changes their environment maps without replacing
images, mounts, commands, ports, networks or dependencies. It is local source-custody wiring,
not a production security profile, key registry, producer qualification or institutional approval.

| Input | Scope and default |
| --- | --- |
| `ENTERPRISE_AUTH_CONTEXT_HMAC_SECRET` | Required nonempty operator-owned secret; no committed or generated fallback. Both services verify the existing protocol. |
| `ENTERPRISE_PRIMARY_KEY_ID` | Required nonempty ID of that existing operator-owned key; no new issuer or identity is created. |
| `ENTERPRISE_AUTH_CONTEXT_MAX_AGE_SECONDS` | Fixed at 300 seconds in this overlay; fresh signed request contexts remain necessary. |
| `ENTERPRISE_ENFORCE_AUTHZ` | Fixed `true` in both selected services; affected write requests require verified identity and applicable service-owned capabilities. |
| `ENTERPRISE_ENFORCE_READ_AUTHZ` | Fixed `true` in QCP; affected read requests, including registered source-product queries, require verified identity and capabilities. |
| `LOTUS_PORTFOLIO_SOURCE_SUBMISSION_GRANTS_JSON` | Ingestion only; default `[]`. Existing exact tenant/portfolio/producer/family submission grants. |
| `LOTUS_PORTFOLIO_REGISTRY_SOURCE_GRANTS_JSON` | Ingestion only; default `[]`. Existing exact tenant/source/scope/product grants. |
| `PORTFOLIO_NEUTRAL_SOURCE_READ_GRANTS_JSON` | QCP only; default `[]`. Independent exact consumer/tenant/source/scope/product grants. |
| `LOTUS_CORE_CAP_HISTORICAL_REGISTRY_READ_ENABLED` | QCP only; default `false`. Enablement is separate from authorization. |
| `LOTUS_CORE_CAP_FINANCIAL_SOURCE_CUT_READ_ENABLED` | QCP only; default `false`. Enablement is separate from authorization. |

Without either required input, Compose's `${NAME:?message}` interpolation refuses the overlay
for unset or empty values. Operator review must also reject whitespace-only key IDs.
The existing verifier refuses a missing or blank signing secret,
wrong keys, invalid signatures and stale contexts. Native parsers retain bounded exact grant
shapes and wildcard refusal. Authentication alone supplies no grant: source observations remain
producer `unqualified`, and joined source compatibility/financial authority remain unavailable
without separately admitted independent evidence. The unchanged base and other services keep
their existing enforcement settings. This overlay does not enroll fact-verification keys/cuts.

This is an enforcing opt-in profile, not transparent key-only forwarding. Enroll every affected
ingestion/QCP caller with its existing verified service/actor/tenant identity and exact required
capabilities, and sign those requests before activation. Unauthenticated health/documentation
exemptions remain governed by existing middleware; unsigned application calls are not exempt.
A configured secret/key alone is insufficient when middleware enforcement is disabled: the
standalone verifier may accept a signature while the request context remains unverified and
native source admission refuses it. Configuration tests must exercise installed middleware,
request-context propagation and source-boundary refusals, not just individual verifier helpers.

Activation is an operator-owned runtime change after source review and explicit environment
admission. Use an external access-controlled env file populated by the existing secret mechanism;
never commit it, print expanded Compose configuration, or place secret values in shell history.
The operator must review exact producer/observer principals, capabilities, tenant/book/scope,
grant rows, selected read features, source provenance and compatible runtime/calendar first.
The base dependency stack must already be healthy. These commands recreate only the two services;
they do not start dependencies, rebuild images, reset data or establish native acceptance.

Working directory: accepted `lotus-core` checkout. PowerShell:

```powershell
Set-Location (Join-Path $env:LOTUS_WORKSPACE_ROOT 'lotus-core')
if (-not $env:LOTUS_SOURCE_CUSTODY_ENV_FILE -or
    -not (Test-Path -LiteralPath $env:LOTUS_SOURCE_CUSTODY_ENV_FILE -PathType Leaf)) {
    throw 'Set LOTUS_SOURCE_CUSTODY_ENV_FILE to the reviewed external operator env file.'
}
docker compose --env-file "$env:LOTUS_SOURCE_CUSTODY_ENV_FILE" -f docker-compose.yml -f docker-compose.source-custody.yml config --quiet
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
docker compose --env-file "$env:LOTUS_SOURCE_CUSTODY_ENV_FILE" -f docker-compose.yml -f docker-compose.source-custody.yml up -d --no-deps ingestion_service query_control_plane_service
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
```

POSIX:

```bash
cd "$LOTUS_WORKSPACE_ROOT/lotus-core"
: "${LOTUS_SOURCE_CUSTODY_ENV_FILE:?Set the reviewed external operator env-file path}"
test -f "$LOTUS_SOURCE_CUSTODY_ENV_FILE" || exit 1
docker compose --env-file "$LOTUS_SOURCE_CUSTODY_ENV_FILE" -f docker-compose.yml -f docker-compose.source-custody.yml config --quiet || exit $?
docker compose --env-file "$LOTUS_SOURCE_CUSTODY_ENV_FILE" -f docker-compose.yml -f docker-compose.source-custody.yml up -d --no-deps ingestion_service query_control_plane_service || exit $?
```

Host environment variables take precedence over an env file; the operator must reconcile existing
values without exposing them. Native Docker interpolation/merge, deployed key presence, exact
principal/grant admission, PostgreSQL persistence, source-off/restart and financial-cut acceptance
are separate runtime proofs. Source tests check the overlay's bounded interpolation projection,
merge intent and existing verifier/grant behavior; they do not execute Docker. Withdraw the overlay
only through the runtime owner using a reviewed base environment without these opt-in credentials
and recreate these same two services. Preserve source facts, receipts, exports and volumes.


## Analytics Export Job Permissions

QCP owns three exact default capability rules for both portfolio and position analytics exports:

| Operation | Required signed capability |
| --- | --- |
| `POST /integration/exports/analytics-timeseries/jobs`, including `refresh_of_job_id` | `core.analytics_exports.write` |
| `GET /integration/exports/analytics-timeseries/jobs/{job_id}` | `core.analytics_exports.read` |
| `GET /integration/exports/analytics-timeseries/jobs/{job_id}/result`, including JSON, NDJSON and gzip | `core.analytics_exports.read` |

These defaults apply without `ENTERPRISE_CAPABILITY_RULES_JSON`. Read permission cannot create or
refresh a job; write permission alone cannot read status or results. Authorization is enforced
only when the corresponding existing write/read flags are enabled. With enforcement and
`ENTERPRISE_REQUIRE_CAPABILITY_RULES=true`, an unmapped protected route refuses with
`missing_capability_rule`. The current operator JSON map can replace an exact default; review the
effective policy rather than assuming overrides are additive. Method and path templates are exact;
no export subtree wildcard is required.

QCP registers only the concrete export-job POST operation as write-only for flag selection.
`ENTERPRISE_ENFORCE_READ_AUTHZ` alone does not protect creation or refresh. This operation
classification is immutable and independent of the operator's capability name; an exact override
still replaces the required capability. Existing mapped source-product POST queries retain their
read-authorization protection and their existing write-flag behavior.

| Write flag | Read flag | Export create/refresh authorization | Export status/result authorization |
| --- | --- | --- | --- |
| Off | Off | Off | Off |
| Off | On | Off | On |
| On | Off | On | Off |
| On | On | On | On |

This table describes only capability authorization. Tenant admission, payload validation and
source grants remain independent. `ENTERPRISE_REQUIRE_CAPABILITY_RULES` does not turn authorization
on; it denies a missing mapping after identity verification on an enforced request. A mapped
capability is required under enforcement whether strict rule coverage is enabled or disabled.

The source-custody overlay does not enable strict rule coverage. These three defaults do not make
all QCP routes ready for strict activation. Enroll every affected caller and review its exact
routes before the operator changes enforcement. Canonical `tenant-sg` enrollment is separate from
isolated synthetic tenants. Neutral registry/cut reads still require literal `lotus-manage`, their
own source-data capabilities, exact grants and enabled features. A producer must still match its
declared source system; export permissions confer neither that identity nor a source grant.

Export permissions cover job lifecycle operations across both datasets. They do not establish
tenant ownership of a retained job, source qualification, financial completeness or institutional
approval. Tenant isolation and the remaining QCP/operator rule coverage require separate evidence;
do not infer either from a successful capability check. Preserve original exports and corrections.

## Retained Reads

QCP registers two exact POST collections:

- `/integration/portfolio-historical-registries/query`, views `CUT`, `MEMBERS`, `CAPTURES`.
- `/integration/financial-source-cuts/query`, selected portfolio views `CUT`, `INPUTS`, `CAPTURES`.

Select the exact source system, registry scope, cut, revision and bare batch hash. Financial
queries also select the portfolio in the body. Required page controls include a bounded page size
and nullable signed continuation token. Tokens bind tenant, admitted service, route/product,
all selectors/root, view, page size, ordering and last immutable key. Neither numeric caller
offsets nor latest aliases are accepted.

Read features default disabled: `LOTUS_CORE_CAP_HISTORICAL_REGISTRY_READ_ENABLED` and
`LOTUS_CORE_CAP_FINANCIAL_SOURCE_CUT_READ_ENABLED`. Enabling a feature does not grant access.
`PORTFOLIO_NEUTRAL_SOURCE_READ_GRANTS_JSON` separately requires exact `service_identity`,
`tenant_id`, `source_system`, `registry_scope_id` and supported `products`. Existing source-data
read capabilities and verified enterprise authorization remain required. Empty defaults grant nothing.

Completed reads use retained bytes/context only. They expose the batch and independent selected
graph roots; a selected graph does not require unrelated portfolios. Absent, incomplete and
complete-empty cuts remain distinct. Original native receipt time and retained completion
materialization time are not replaced by the current read time.
Completed source receipts require aware timestamps and completion at or after receipt;
equal times are valid. This chronology check imposes no source freshness policy. Excessive
JSON nesting is a malformed input refusal rather than an unhandled parser error.

## Worker Controls And Recovery

| Setting | Default | Bounds |
| --- | --- | --- |
| `LOTUS_FINANCIAL_SOURCE_CUT_WORKERS` | 1 | 1–8 |
| `LOTUS_FINANCIAL_SOURCE_CUT_LEASE_SECONDS` | 30 | 10–300 |
| `LOTUS_FINANCIAL_SOURCE_CUT_RETRY_SECONDS` | 5 | 1–60 |
| `LOTUS_FINANCIAL_SOURCE_CUT_IDLE_MILLISECONDS` | 500 | 50–10000 |

The shared strict runtime configuration policy applies. Claims use database time, exact tenant,
command/scope/checkpoint hashes, token and expiry. Expired workers cannot checkpoint or emit.
Restartable parent phases verify raw chunks, ordered members/inputs and registry mappings before
spawning indexed capture partitions. Native acquisition occurs outside write transactions.
Segment writes renew fenced leases in short transactions; full retained raw hashes are checked
before capture links earn completion. Shared cache races reuse the winning immutable artifact;
unrelated database failures propagate to supervision.

| Symptom | Meaning and next action |
| --- | --- |
| Source unavailable or missing retained export/page context | Job stays pending; restore the exact pinned source, not a fabricated empty response |
| Typed/raw/order/population reconciliation failure | Manifest work fails; inspect original declaration/receipt and submit an explicit corrected revision |
| Correction waits on predecessor custody | Complete or fail the predecessor before sealing its successor |
| Stale worker token/expiry | The claim may mutate nothing; another worker can reclaim expired work |
| Native capture currency contradicts selected graph | Explicit unavailable; cache reuse cannot bypass source currency checks |
| Read feature/grant absent | Read access remains unavailable; an enabled capability alone is insufficient |

Never edit immutable evidence to repair it. Corrections preserve prior graphs/bytes and require
exact predecessor/head CAS. Failed predecessors can be explicitly corrected; pending predecessors
cannot be overtaken, preserving scope order of completion notices. Nonempty custody cannot be
downgraded. Unknown dependent objects refuse destructive DDL rather than being dropped by CASCADE.

## Validation Commands

Working directory: the `lotus-core` checkout. These commands run source/unit controls only;
they do not start Docker, connect to PostgreSQL or enroll any source authority.

PowerShell:

```powershell
Set-Location "$env:LOTUS_WORKSPACE_ROOT/lotus-core"
python scripts/development/repository_python.py -m pytest tests/unit/services/persistence_service/infrastructure/test_financial_source_capture_client.py tests/unit/services/persistence_service/repositories/test_financial_source_cut_work_repository.py -q -W error
python scripts/development/repository_python.py scripts/quality/route_contract_family_guard.py
```

POSIX:

```bash
cd "$LOTUS_WORKSPACE_ROOT/lotus-core"
python scripts/development/repository_python.py -m pytest tests/unit/services/persistence_service/infrastructure/test_financial_source_capture_client.py tests/unit/services/persistence_service/repositories/test_financial_source_cut_work_repository.py -q -W error
python scripts/development/repository_python.py scripts/quality/route_contract_family_guard.py
```

The prepared owning PostgreSQL files require an explicitly admitted dependency; unit results
cannot substitute for their execution. Preserve the broader S/M/L/D/H, flow-v2 separate
window/dependency roots, version/reversal handoffs and Manage/Performance acceptance obligations.
The [methodology](../methodologies/source-data-products/portfolio-financial-source-cuts.md)
defines commitments and serializer boundaries.
