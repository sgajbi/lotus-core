# RFC 046 - Automated Demo Data Pack Bootstrap for End-to-End Platform Validation

- Status: Proposed
- Date: 2026-02-24
- Authors: lotus-core Engineering
- Related:
  - `docs/RFCs/RFC 035 - lotus-core lotus-performance lotus-manage Responsibility and Integration Contract.md`
  - `docs/RFCs/RFC 036 - lotus-core Core Snapshot Contract for lotus-performance and lotus-manage.md`
  - `docs/RFCs/RFC 043 - lotus-core Core Snapshot Contract Hardening (Freshness, Lineage, Section Governance).md`
  - `lotus-platform/Local Development Runbook.md`

## 1. Problem Statement

Local and demo environments lack a reliable, automated, and realistic reference dataset that is loaded as part of platform startup. Teams currently rely on manual ingestion or ad-hoc test payloads, which causes:

- inconsistent UI/lotus-gateway/lotus-core/lotus-performance/lotus-manage behavior across developer machines,
- weak validation of end-to-end lifecycle processing,
- reduced confidence in positions, valuation, performance, and risk outputs,
- slow feedback loops for UX and integration improvements.

## 2. Root Cause

1. No standardized demo data pack artifact owned by lotus-core.
2. No compose-time orchestration step to ingest and verify a common dataset.
3. No deterministic readiness checks proving that downstream processing has completed.
4. Existing sample data is fragmented across tests and not packaged for startup automation.

## 3. Decision

Introduce a lotus-core-owned automated demo data pack workflow that:

1. defines a comprehensive, realistic multi-portfolio bundle (portfolios, instruments, transactions, market prices, FX rates, business dates),
2. ingests the bundle through lotus-core ingestion APIs (same path used by platform integrations),
3. verifies downstream processing via lotus-core query APIs (positions, transactions, analytics-ready outputs),
4. runs automatically as a one-shot container during `docker compose up -d --build`.

## 4. Scope

In scope:

- a deterministic demo dataset with multiple product types and transaction lifecycle events,
- an executable bootstrap tool in `tools/`,
- compose integration for auto-run and startup validation,
- tests for tool behavior and docs updates for local run commands.

Out of scope:

- changing lotus-performance or lotus-manage internals,
- synthetic data generation service beyond lotus-core bootstrap,
- replacing existing E2E test fixtures.

## 5. Proposed Solution

### 5.1 Demo Data Pack Content

The pack will include:

- multiple portfolios (advisory, discretionary, income, and balanced patterns),
- cross-asset instruments (cash, equities, bonds, ETFs/funds),
- transaction history (deposit, buy, sell, dividend, fee, transfer/withdrawal flows),
- daily market prices and FX rates for valuation and analytics,
- business dates needed for timeseries and aggregation outputs.

### 5.2 Automation Flow

On startup:

1. wait for ingestion/query readiness,
2. check whether demo portfolios already exist (idempotent guard),
3. ingest portfolio bundle if missing,
4. poll query endpoints until expected outputs are present for each demo portfolio,
5. exit success/failure with clear logs for operators.

### 5.3 Compose Integration

Add a one-shot service (`demo_data_loader`) to lotus-core compose:

- depends on lotus-core runtime services,
- executes `python -m tools.demo_data_pack --ingest --verify`,
- exits after successful validation,
- supports env-driven toggles (enabled/disabled, timeout, strict verification).

## 6. Architectural Impact

- Reinforces lotus-core role as canonical data and lifecycle processing owner.
- Improves integration readiness for lotus-gateway/UI/lotus-performance/lotus-manage by guaranteeing baseline data availability.
- Converts demo-data readiness into a repeatable platform bootstrap step instead of manual operations.

## 7. Risks and Trade-offs

Risks:

- startup time increases due to ingestion + verification wait.
- false negatives if readiness timeouts are too aggressive on slower machines.
- stale/static demo composition may drift from evolving product requirements.

Mitigations:

- configurable timeout and enable/disable flag,
- concise logs with failed endpoint context,
- periodic updates to dataset through RFC-governed changes.

## 8. Implementation Plan (High Level)

1. Implement `tools/demo_data_pack.py` with:
   - deterministic payload builder,
   - ingestion/query client helpers,
   - retry + poll + verification loop,
   - CLI flags for ingest-only, verify-only, timeout.
2. Add compose service for auto bootstrap.
3. Add tests validating payload coverage and idempotent flow behavior.
4. Update lotus-core README/runbook sections for startup and troubleshooting.
5. Add cross-repo clarification in `lotus-platform` if startup workflow changes.

## 9. Success Criteria

1. `docker compose up -d --build` on lotus-core automatically loads demo data without manual API calls.
2. Demo portfolios are visible through lotus-core query APIs and lotus-gateway/UI screens.
3. Core lifecycle outputs (positions, valuations, analytics-ready endpoints) are available after bootstrap.
4. Re-running bootstrap does not create unintended duplicate business records.

