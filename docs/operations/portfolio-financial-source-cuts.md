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
