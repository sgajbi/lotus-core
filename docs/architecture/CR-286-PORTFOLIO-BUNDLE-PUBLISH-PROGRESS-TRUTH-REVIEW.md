# CR-286: Portfolio bundle publish progress truth

Date: 2026-03-14

## Summary
- Hardened portfolio-bundle ingestion failures so the stored failure reason now includes which
  bundle entity groups had already published before the bundle stopped.

## Problem
- `publish_portfolio_bundle(...)` fans one mixed request into six domain publish paths.
- On failure, the raised `IngestionPublishError` only described the failing sub-publish.
- That lost important causal context:
  - earlier entity groups may already have been fully published
  - later entity groups were never reached
- The ingestion job failure record therefore told operators which record failed, but not how far
  the bundle had already progressed across domains.

## Change
- Added `published_counts` tracking inside `publish_portfolio_bundle(...)`.
- Wrapped inner `IngestionPublishError` instances with a bundle-level message that includes the
  already-published entity-group counts at the moment the bundle stopped.
- Preserved:
  - original `failed_record_keys`
  - original `published_record_count`

## Why this matters
- This keeps the failure evidence honest for mixed-file and UI bundle workflows.
- Operators can now see:
  - which domain groups were already emitted
  - which group failed next
- That is materially better for:
  - support diagnosis
  - targeted replay decisions
  - avoiding false assumptions that the whole bundle failed before any publish happened

## Evidence
- Unit proof:
  - `tests/unit/services/ingestion_service/services/test_ingestion_service.py`
  - proves that when business dates publish successfully and portfolios fail next, the raised
    bundle error includes:
    - `business_dates: 1`
    - `portfolios: 0`
    - later groups still at `0`

## Validation
- `python -m pytest tests/unit/services/ingestion_service/services/test_ingestion_service.py tests/integration/services/ingestion_service/test_ingestion_routers.py -q`
- `python -m ruff check src/services/ingestion_service/app/services/ingestion_service.py tests/unit/services/ingestion_service/services/test_ingestion_service.py`

## Follow-up
- If we later want richer ingestion job diagnostics, this bundle progress map is a good precedent
  for explicit structured progress metadata rather than message-only context.
