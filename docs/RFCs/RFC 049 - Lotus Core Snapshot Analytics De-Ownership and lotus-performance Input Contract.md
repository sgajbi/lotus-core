# RFC 049 - lotus-core Core Snapshot Analytics De-Ownership and lotus-performance Input Contract

## 1. Problem Statement
lotus-core `core-snapshot` currently allows `PERFORMANCE` and `RISK_ANALYTICS` sections. This blurs service ownership and duplicates analytics responsibility with lotus-performance.

## 2. Decision
- lotus-core remains system-of-record for portfolio ledger, transactions, positions, valuation, and time-series.
- lotus-performance is the analytics owner for performance and advanced analytics.
- lotus-core `core-snapshot` contract will no longer serve analytics-owned sections (`PERFORMANCE`, `RISK_ANALYTICS`).
- lotus-core introduces a raw integration contract for lotus-performance: `POST /integration/portfolios/{portfolio_id}/performance-input`.

## 3. Contract Changes
- `core-snapshot` governance filters analytics sections and emits warning `ANALYTICS_SECTIONS_DELEGATED_TO_PA` (or rejects in strict mode).
- New endpoint returns raw valuation points:
  - `perfDate`, `beginMv`, `bodCf`, `eodCf`, `mgmtFees`, `endMv`
  - plus `performanceStartDate`, `portfolioId`, `baseCurrency`.

## 4. Architectural Impact
- Clear separation of concerns:
  - lotus-core: data processing + standardized serving.
  - lotus-performance: analytics computation and analytics APIs.
- lotus-gateway/UI remain stable while analytics ownership is moved to lotus-performance.

## 5. Risks and Trade-Offs
- Existing consumers requesting analytics sections from `core-snapshot` may see filtered sections.
- Transitional complexity while all consumers adopt lotus-performance-based analytics paths.

## 6. Implementation Plan
1. Add performance-input endpoint and DTOs in lotus-core integration contract.
2. Enforce analytics section de-ownership in `core-snapshot` governance.
3. Update capability metadata to advertise raw performance input contract instead of lotus-core baseline analytics.
4. Update downstream consumers (lotus-performance/lotus-gateway) and tests.

