# RFC 048 - One-Year Demo History and Valuation Continuity for lotus-performance UI

- Status: Implemented
- Date: 2026-02-24
- Authors: lotus-core Engineering
- Related:
  - `docs/RFCs/RFC 046 - Automated Demo Data Pack Bootstrap for End-to-End Platform Validation.md`
  - `docs/RFCs/RFC 047 - Position Materialization Guarantees for Multi-Portfolio Demo Data.md`

## 1. Problem Statement

Demo data was not sufficient for reliable year-scale portfolio analytics and UI review:

1. Demo history was short and static.
2. Fallback holdings from `position_history` lacked valuation fields when latest snapshots lagged.
3. Result: lotus-performance/lotus-gateway/UI workflows surfaced null valuation context for multiple demo portfolios.

## 2. Root Cause

1. Demo data generator used a short, fixed date window.
2. Query fallback path prioritized position continuity but did not enrich valuation.
3. Demo bootstrap did not force-refresh stale datasets.

## 3. Proposed Solution

1. Generate one-year business-date history for demo data pack, ending at current date.
2. Keep deterministic transaction terminal states while spreading activity over the year.
3. Force demo ingestion on startup to avoid stale local state drift.
4. Enrich fallback position rows with latest snapshot valuation if available.
5. Provide cost-basis valuation continuity when snapshots are not yet materialized.

## 4. Architectural Impact

1. Improves end-to-end demo determinism and usability for lotus-performance/lotus-gateway/UI.
2. Makes holdings valuation non-null under degraded snapshot materialization conditions.
3. Reduces false-negative UI failures due to asynchronous valuation backfill timing.

## 5. Risks and Trade-offs

1. Fallback cost-basis valuation is a continuity approximation, not mark-to-market truth.
2. Larger demo data pack increases bootstrap processing volume.

## 6. High-Level Implementation Approach

1. Update `tools/demo_data_pack.py` to generate one-year dates and dynamic transaction timestamps.
2. Enable `--force-ingest` for compose demo loader.
3. Extend query position fallback valuation behavior.
4. Verify via API checks on demo portfolios and lotus-gateway portfolio-360 output.
