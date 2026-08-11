# API-First Operational Playbook

This runbook defines the required API-first troubleshooting approach for `lotus-core`.

Do not use direct database queries for standard support workflows.

## Required Support APIs

Use these endpoints as the canonical operational surfaces:

1. `GET /support/portfolios/{portfolio_id}/overview`
2. `GET /support/portfolios/{portfolio_id}/valuation-jobs`
3. `GET /support/portfolios/{portfolio_id}/aggregation-jobs`
4. `GET /support/portfolios/{portfolio_id}/corporate-action-events`
5. `GET /lineage/portfolios/{portfolio_id}/keys`
6. `GET /lineage/portfolios/{portfolio_id}/securities/{security_id}`

## Core Troubleshooting Flows

### Reprocessing or stale position concerns

1. Call `/support/portfolios/{portfolio_id}/overview` to validate queue pressure and freshness markers.
2. Call `/lineage/portfolios/{portfolio_id}/keys?reprocessing_status=REPROCESSING` to find active keys.
3. Call `/lineage/portfolios/{portfolio_id}/securities/{security_id}` for a key-level epoch/watermark state.

### Valuation backlog or failures

1. Call `/support/portfolios/{portfolio_id}/valuation-jobs?status_filter=PENDING`.
2. Call `/support/portfolios/{portfolio_id}/valuation-jobs?status_filter=FAILED`.
3. For a failing key, inspect `/lineage/portfolios/{portfolio_id}/securities/{security_id}`.

### Aggregation backlog

1. Call `/support/portfolios/{portfolio_id}/aggregation-jobs?status_filter=PENDING`.
2. Correlate with `/support/portfolios/{portfolio_id}/overview`.
3. Inspect logs/metrics for scheduler and consumer behavior.

### Corporate-action cohort readiness or ordered release

1. Call `/support/portfolios/{portfolio_id}/corporate-action-events` with `tenant_id`,
   `legal_book_id`, matching `X-Tenant-Id`, and the privileged `core.support.read` capability.
2. Filter by `readiness_status` to distinguish incomplete source authority from invalid graph or
   child evidence; use `execution_status` for pending, processing, failed, superseded, or complete
   release posture.
3. Treat `200 total=0` as a valid empty/filter-empty result. Treat 404 as absent or wrong exact
   tenant/book/portfolio scope. Do not infer failure from an empty page.
4. Use the stable finding reason codes, manifest/plan hashes, fence and progress counters for
   triage. Do not request raw payloads or mutate the ledgers directly; use governed replay or
   reprocessing controls.

## Escalation Rule

If support/lineage APIs show inconsistent state versus observed API behavior:

1. capture `X-Correlation-ID` from failing requests,
2. collect relevant support/lineage API payloads,
3. attach service logs and metrics around the same correlation window.
