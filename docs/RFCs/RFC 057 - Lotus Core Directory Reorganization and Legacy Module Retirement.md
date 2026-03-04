# RFC 057 - Lotus Core Directory Reorganization and Legacy Module Retirement

- Status: Implemented
- Date: 2026-02-27
- Authors: lotus-core maintainers
- Related: RFC 035, RFC 036, RFC 046A, RFC 049, RFC 056, lotus-platform standards
- Implementation: Completed on 2026-02-27 via PRs #83, #84, #85, #86, #87, #88

## Problem Statement

`lotus-core` has evolved through multiple ownership phases. Current code and docs include mixed-era structures and legacy assets that no longer reflect the target role of lotus-core:

1. Legacy analytics modules and docs remain in-repo (`risk`, `performance`, `concentration`) even after ownership moved out.
2. Directory boundaries are service-centric but not consistently layered; domain logic, adapters, and transport details are mixed.
3. API and contract drift exists between lotus-core and downstream expectations (notably integration/analytics contract surfaces).
4. Some documentation still suggests direct DB investigation as an operational norm, which conflicts with API-first boundaries.
5. Demo/UI onboarding flows are mixed with production ingestion paths without explicit boundary/feature-mode separation.

Risks introduced:

- Increased refactor cost and ambiguity in ownership.
- Incorrect consumer behavior (calling deprecated or missing surfaces).
- Higher chance of accidental reintroduction of out-of-scope analytics logic into lotus-core.
- Slower onboarding due to unclear module intent and stale docs.

## Goals

1. Reorganize `lotus-core` into clean, scalable boundaries aligned to current ownership.
2. Remove legacy modules/directories that no longer belong to lotus-core ownership.
3. Enforce API-first integration (no downstream direct DB coupling).
4. Align ingestion model to external-upstream reality, while preserving multi-modal ingestion (Kafka/REST/File).
5. Preserve and harden simulation workflows as first-class lotus-core capability.
6. Provide incremental migration path with low operational risk and clear PR slices.

## Non-Goals

1. Rebuilding analytics services now owned by other apps.
2. Large new feature expansion unrelated to restructuring.
3. Breaking stable public contracts without explicit deprecation plan and approval.

## Current Findings (Repository Review)

### A. Legacy modules/directories identified

Code-level legacy candidates:

1. `src/libs/risk-analytics-engine`
2. `src/libs/performance-calculator-engine`
3. `src/libs/concentration-analytics-engine`

Doc-level legacy candidates:

1. `docs/features/risk_analytics`
2. `docs/features/performance_analytics`
3. `docs/features/concentration_analytics`
4. `docs/features/portfolio_review`
5. `docs/features/portfolio_summary`

Config/runtime stale references:

1. `docker-compose.yml` mounts still include:
 - `./src/libs/risk-analytics-engine:/app/src/libs/risk-analytics-engine`
 - `./src/libs/concentration-analytics-engine:/app/src/libs/concentration-analytics-engine`

### B. Duplicated/overlapping responsibilities

1. `positions` vs `positions-analytics` overlap:
 - `GET /portfolios/{id}/positions` already exposes quantities, cost basis, valuation, asset class.
 - `POST /portfolios/{id}/positions-analytics` re-computes/re-aggregates valuation + income + instrument enrichment and creates a second position-level contract surface.
2. Ingestion mode overlap:
 - canonical entity ingestion routers (`/ingest/portfolios`, `/ingest/transactions`, etc.)
 - plus bundle ingestion (`/ingest/portfolio-bundle`)
 - plus upload preview/commit (`/ingest/uploads/*`) for UI/manual onboarding.

### C. Ingestion paths vs external-upstream model

1. Upload preview/commit and portfolio-bundle APIs are currently positioned as onboarding paths; these should be explicitly marked as adapter/edge paths (not canonical enterprise upstream mode).
2. Canonical upstream should remain: external producer -> ingestion API/event -> Kafka -> persistence.

### D. API-first and DB bypass findings

No direct downstream runtime DB coupling was found in peer services during scan (downstream systems mostly call lotus-core APIs).  
However, the following need governance decisions:

1. Docs still encourage direct DB monitoring for operations:
 - `docs/features/reprocessing_engine/04_Operations_Troubleshooting_Guide.md`
2. Local test harness and infra understandably use DB URLs (`HOST_DATABASE_URL`, migration runner), which is acceptable for internal testing but should not be interpreted as downstream integration guidance.

## Additional Required Finding: PositionAnalytics and Positions Endpoints

### What `PositionAnalytics` currently provides

Endpoint:

- `POST /portfolios/{portfolio_id}/positions-analytics`

Current responsibilities:

1. Fetch current holdings baseline.
2. Enrich with instrument metadata.
3. Compute weights by total market value.
4. Provide valuation details (market value, cost basis, unrealized P&L in local/base).
5. Aggregate income cashflows and FX conversion for base-currency income.
6. Return section-selective payload (`BASE`, `INSTRUMENT_DETAILS`, `VALUATION`, `INCOME`).

Who/what calls it:

1. Exposed by lotus-core query service.
2. Consumed by `lotus-performance` transitional adapter (`PasInputService`) to normalize downstream analytics contracts.

### Does it duplicate/fragment analytics?

Yes, partially.

1. It duplicates position-level valuation/cost-basis data already available in `positions`.
2. It introduces a second, richer position contract that can become a parallel analytics surface.
3. It increases risk of contract drift between core holdings APIs and analytics-oriented consumers.

### Recommendation for positions contract target

Recommended target model:

1. `positions` APIs become canonical for position-level core state:
 - quantity
 - cost basis
 - valuation
 - unrealized P&L
 - income aggregates that are directly ledger-derived
2. Keep advanced analytics (attribution-style, higher-order risk/performance transforms) out of lotus-core-owned position contract.
3. If sectioned enrichment is still needed, expose it as explicit subresources of positions (same canonical vocabulary) rather than a parallel top-level analytics contract.

Approved direction:

1. Consolidate `positions-analytics` into canonical `positions` resources.

## Proposed Target Architecture

### Module boundaries

1. `src/domain/`
 - canonical business models and invariants (portfolio, transaction, position, valuation, cashflow, timeseries, simulation)
2. `src/application/`
 - use cases/orchestration services (ingestion commands, query use cases, simulation flows)
3. `src/adapters/`
 - transport/storage integrations:
   - `api/rest`
   - `messaging/kafka`
   - `storage/postgres`
   - `files/upload`
4. `src/platform/`
 - cross-cutting concerns (logging, observability, config, health, policy guards)
5. `src/services/`
 - deployable service entrypoints only (thin wiring to application/domain/adapters)
6. `tests/`
 - organized by boundary (`unit/domain`, `unit/application`, `integration/adapters`, `e2e/contracts`)

### Layering rules (strict dependency direction)

1. `domain` depends on nothing above it.
2. `application` depends on `domain` only.
3. `adapters` depend on `application`/`domain`.
4. `services` compose adapters + application; no business logic in service entrypoints.
5. No adapter-to-adapter coupling without explicit interface in `application`.

## Proposed Directory Tree

### Before (high-level)

```text
src/
  libs/
    portfolio-common/
    financial-calculator-engine/
    risk-analytics-engine/                (legacy)
    performance-calculator-engine/        (legacy)
    concentration-analytics-engine/       (legacy)
  services/
    ingestion_service/
    persistence_service/
    query_service/
    calculators/
    timeseries_generator_service/
docs/features/
  risk_analytics/                         (legacy)
  performance_analytics/                  (legacy)
  concentration_analytics/                (legacy)
  portfolio_review/                       (legacy)
  portfolio_summary/                      (legacy)
```

### Target (conceptual)

```text
src/
  domain/
    portfolio/
    transaction/
    position/
    valuation/
    cashflow/
    timeseries/
    simulation/
  application/
    ingestion/
    query/
    simulation/
    reprocessing/
  adapters/
    api/
      ingestion_rest/
      query_rest/
    messaging/
      kafka/
    storage/
      postgres/
    files/
      bulk_upload/
  platform/
    config/
    observability/
    policy/
    health/
  services/
    ingestion_service/
    persistence_service/
    query_service/
    calculators/
    timeseries_generator_service/
tests/
  unit/
  integration/
  e2e/
docs/
  features/
    core_*                                (core-owned only)
  archived/
    legacy_analytics/                     (migrated ownership docs)
```

## Legacy Removal Plan

### Modules/dirs to delete (proposed)

Code:

1. `src/libs/risk-analytics-engine`
2. `src/libs/performance-calculator-engine`
3. `src/libs/concentration-analytics-engine`

Docs (or archive out of active feature docs):

1. `docs/features/risk_analytics`
2. `docs/features/performance_analytics`
3. `docs/features/concentration_analytics`
4. `docs/features/portfolio_review`
5. `docs/features/portfolio_summary`

Config cleanup:

1. remove legacy volume mounts from `docker-compose.yml`
2. remove stale references in docs and RFC index/readme pages

### Replacement/migration mapping

1. Risk analytics ownership -> `lotus-risk`.
2. Performance analytics ownership -> `lotus-performance`.
3. Concentration analytics ownership -> `lotus-risk`.
4. Summary/review ownership -> `lotus-report`.
5. lotus-core retains only canonical data + core calculations + simulation and integration contracts.

## Contract and Compatibility Plan

Stable contracts to keep:

1. Canonical ingestion and query APIs used by downstream.
2. Simulation session APIs.
3. Integration policy/capabilities APIs.

Compatibility strategy:

1. No legacy compatibility retained in `lotus-core` for removed ownership domains.
2. Remove legacy analytics/reporting/integration contract surfaces from `lotus-core` in this restructuring.
3. Downstream app fixes are explicitly out-of-scope for this RFC execution and will be handled in downstream repos later.
4. Enforce API vocabulary and no-alias gates for all retained contracts.

## Risk Assessment and Mitigations

### Key risks

1. Downstream breakage from hidden dependencies on deprecated contracts.
2. Behavioral drift during directory moves/refactors.
3. Operational blind spots if DB-based runbooks are removed without API alternatives.

### Mitigations

1. Characterization tests for all retained contracts before moves.
2. Move-only PRs first (no logic changes), then deletion PRs.
3. Contract smoke tests across lotus-core, lotus-gateway, lotus-performance, lotus-report.
4. Keep operational support APIs (`/support/*`, `/lineage/*`) as DB-query replacement path.

## Approved Decisions

1. **PositionAnalytics future**
 - Approved: merge `positions-analytics` into canonical `positions` contract surface.

2. **Upload/Bundle onboarding in production scope**
 - Approved: keep as adapter mode, explicitly feature-flagged and documented as non-canonical.

3. **Direct DB guidance in docs**
 - Approved: remove DB query guidance and replace with API-first operational playbooks.
 - Required API support to replace DB troubleshooting:
   - `/support/portfolios/{portfolio_id}/overview`
   - `/support/portfolios/{portfolio_id}/valuation-jobs`
   - `/support/portfolios/{portfolio_id}/aggregation-jobs`
   - `/lineage/portfolios/{portfolio_id}/keys`
   - `/lineage/portfolios/{portfolio_id}/securities/{security_id}`

4. **Downstream contract drift (`integration/portfolios/*`)**
 - Approved: remove legacy `integration/portfolios/*` expectations from lotus-core now.
 - Downstream migrations to canonical endpoints will be handled later in downstream app RFC/implementation tracks.

## Observability Requirements for New Boundaries

1. Ingestion boundary:
 - request counters, validation failures, publish success/failure, producer latency, dead-letter metrics
2. API boundary:
 - endpoint latency/error/throughput + correlation IDs + tenant/consumer dimensions
3. Domain pipeline:
 - epoch/watermark progression metrics, job queue lag, reprocessing saturation
4. Simulation:
 - session lifecycle metrics, change application failures, projected response latency
5. Contract governance:
 - explicit metrics/logs for deprecated endpoint access and schema validation failures

## Implementation Plan (Incremental PRs)

1. PR-1: governance and structure scaffolding
 - add architecture/layering docs
 - add lint/import boundaries (where feasible)
 - no runtime behavior changes

2. PR-2: move-only refactor
 - reorganize package layout with compatibility imports
 - no logic changes; tests green

3. PR-3: legacy module retirement
 - remove risk/performance/concentration libs and stale mounts
 - archive/remove stale feature docs

4. PR-4: positions contract consolidation
 - merge PositionAnalytics behavior into canonical positions resources
 - remove parallel PositionAnalytics endpoint/contracts from lotus-core

5. PR-5: ingestion mode hardening
 - enforce explicit mode semantics (canonical vs demo/onboarding adapters)
 - feature flags and docs

6. PR-6: operational API-first hardening
 - replace direct DB troubleshooting guidance with support/lineage API workflows

7. PR-7: downstream drift hard-cut in lotus-core
 - remove legacy integration contract surfaces/assumptions from lotus-core
 - document downstream follow-up work (outside this repo) for canonical endpoint adoption

## Execution Progress

1. Completed: PR-1 governance and structure scaffolding (merged)
 - architecture/layering standards added
 - architecture boundary guard added and wired into Make targets

2. Completed: PR-3 legacy module retirement (merged)
 - legacy feature docs removed from active core feature set
 - stale docker-compose legacy analytics mounts removed

3. Completed: PR-4 positions contract consolidation
 - removed `POST /portfolios/{portfolio_id}/positions-analytics` from lotus-core
 - removed position-analytics DTO/service/router/test/docs stack
 - enriched canonical `GET /portfolios/{portfolio_id}/positions` response with instrument metadata (`isin`, `currency`, `sector`, `country_of_risk`) and core position context (`weight`, `held_since_date`)

4. Completed: PR-5 ingestion mode hardening
 - `/ingest/portfolio-bundle` and `/ingest/uploads/*` are explicitly adapter-mode endpoints
 - feature flags added:
   - `LOTUS_CORE_INGEST_PORTFOLIO_BUNDLE_ENABLED`
   - `LOTUS_CORE_INGEST_UPLOAD_APIS_ENABLED`
 - adapter-disabled requests return explicit `410 Gone` with capability metadata
 - integration capability metadata now reflects adapter-mode flags and supported input modes

5. Completed: PR-6 API-first ops hardening
 - direct DB troubleshooting guidance removed from active operational runbooks
 - API-first support/lineage playbook introduced and linked from troubleshooting guides

6. Completed: PR-7 downstream drift hard-cut in lotus-core
 - removed remaining active test expectations for legacy `integration/portfolios/*` contract usage
 - retained historical RFC records but removed active-runtime expectations from current service tests/docs

## Definition of Done

1. No legacy analytics modules remain in lotus-core source tree.
2. Directory structure reflects approved layering with enforced boundaries.
3. Downstream integrations use API contracts only; no DB bypass assumptions in active docs.
4. Positions/PositionAnalytics decision is implemented and documented.
5. Multi-modal ingestion remains supported with explicit canonical vs adapter modes.
6. All quality gates pass (lint, mypy, openapi, vocabulary, no-alias, migration, tests).
7. Cross-repo integration smoke tests pass for lotus-core consumers.
