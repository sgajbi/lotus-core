# CR-1219 Portfolio Maturity Summary Source Contract

## Objective

Address GitHub issue #686 by adding a Core-owned `PortfolioMaturitySummary:v1` operational read so
downstream consumers can use source-owned maturity posture without reconstructing maturity facts
from raw `HoldingsAsOf` rows.

## Expected Improvement

- Reduces cross-repository methodology leakage into `lotus-idea`.
- Keeps maturity-window counting and next-maturity selection inside `lotus-core`.
- Reuses the existing HoldingsAsOf read path instead of duplicating repository access.
- Publishes supportability reasons for missing lifecycle facts, stale/partial HoldingsAsOf
  evidence, and unsupported maturity-feature indicators.
- Preserves the source-batch lineage boundary by using `request_fingerprint` for this derived
  summary and leaving `source_batch_fingerprint` null unless real source-batch evidence exists.

## Implementation

- Added `PortfolioMaturitySummaryResponse` and `GET /portfolios/{portfolio_id}/maturity-summary`.
- Added `position_maturity_summary.py` as the reusable application helper for maturity-window
  policy, supportability classification, freshness mapping, and deterministic fingerprinting.
- Added `PositionService.get_portfolio_maturity_summary(...)`, which reuses
  `get_portfolio_positions(...)` so effective-date selection, fallback rows, weights, held-since
  evidence, market-price freshness, and runtime metadata stay consistent with HoldingsAsOf.
- Added executable source-data catalog, source-data security profile, route-family registry, and
  repo-native domain-product declaration entries for `PortfolioMaturitySummary:v1`.

## Compatibility Impact

No existing route, DTO, persistence model, database table, or downstream response changed. This is
an additive operational-read source-data product. Existing `HoldingsAsOf:v1` positions and
cash-balances contracts are preserved.

## Boundaries

The current implementation summarizes contractual `instrument.maturity_date` facts only. It does
not certify callable, putable, amortizing, structured-note, lockup, expiry, liquidity, reinvestment,
performance, risk, tax, execution-quality, or OMS acknowledgement methodology. Product
classifications suggesting unsupported lifecycle features degrade the response to partial
supportability instead of allowing downstream systems to infer schedules locally.

## Validation Evidence

- `python -m pytest tests/unit/services/query_service/services/test_position_maturity_summary.py tests/unit/services/query_service/services/test_position_service.py tests/unit/services/query_service/dtos/test_source_data_product_identity.py -q`
  - 41 passed.
- `python -m pytest tests/integration/services/query_service/test_positions_router_dependency.py tests/integration/services/query_service/test_main_app.py -q`
  - 40 passed.
- `python -m pytest tests/unit/test_domain_data_product_contracts.py tests/unit/libs/portfolio-common/test_source_data_products.py tests/unit/libs/portfolio-common/test_source_data_security.py -q`
  - 43 passed.

## Documentation And Wiki Decision

Updated source-data methodology, RFC-0083 catalog, repo context, quality scorecard, and review
ledger. No repo-local wiki source changed because this slice changes API/data-product contract
truth, not operator navigation or runbook behavior.
