# RFC 035 - lotus-core lotus-performance lotus-manage Responsibility and Integration Contract

- Date: 2026-02-23
- Services Affected: `lotus-core`, `lotus-performance`, `lotus-advise`, UI, lotus-gateway
- Status: Proposed (with lotus-core Phase 1 implemented)

## Summary

Define non-overlapping responsibilities and integration contracts across lotus-core, lotus-performance, and lotus-manage so the suite behaves as a coherent end-to-end platform.

## Responsibility Boundaries

1. lotus-core (Core Platform)
   - System of record for portfolios, positions, transactions, instruments, market data.
   - Processing engine for persistence, valuation, cashflow, timeseries generation.
   - Canonical API source for foundational and support/lineage data.
2. lotus-performance (Advanced Analytics)
   - Higher-order analytics: performance attribution, advanced risk, benchmark analytics, model overlays.
   - Consumes lotus-core data/outputs; does not duplicate lotus-core ingestion/persistence pipelines.
3. lotus-manage (Advisory and Discretionary Workflows)
   - Construction, recommendation, optimization, and rebalance workflows.
   - Can run from direct portfolio input or lotus-core-retrieved portfolio state.
4. UI/lotus-gateway
   - Unified operator experience.
   - Orchestrates calls across lotus-core/lotus-performance/lotus-manage and enforces presentation contracts.

## Integration Patterns

1. Direct input pattern
   - lotus-manage/lotus-performance endpoints may accept portfolio payloads directly for simulation and what-if workflows.
2. lotus-core-connected pattern
   - lotus-manage/lotus-performance use portfolio identifiers and fetch canonical state from lotus-core APIs.
3. Upload pattern (UI)
   - UI supports manual and file-driven upload of core entities to lotus-core ingestion APIs.

## lotus-core Phase 1 Implemented

1. Added `POST /ingest/portfolio-bundle` to support single-request upload of mixed portfolio data:
   - business dates
   - portfolios
   - instruments
   - transactions
   - market prices
   - FX rates
2. Maintains existing lotus-core downstream event topics and processing flows.
3. Designed for UI form + file upload onboarding.

## Non-Overlap Guardrails

1. lotus-performance and lotus-manage must not introduce independent copies of lotus-core core entity stores.
2. lotus-core remains source of truth for portfolio lifecycle and state lineage.
3. lotus-performance and lotus-manage outputs are derived/decision layers and should be versioned separately from lotus-core core records.

## Next Steps

1. Add lotus-gateway contract definitions for lotus-core-connected and direct-input modes.
2. Add canonical glossary mapping across lotus-core/lotus-performance/lotus-manage DTOs.
3. Add API-level provenance fields (`source_system`, `as_of_date`, `correlation_id`) for cross-service auditability.

