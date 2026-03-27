# RFC 084 - PB/WM Wealth Reporting and Ledger Query APIs

| Field | Value |
| --- | --- |
| Status | Implemented |
| Created | 2026-03-27 |
| Last Updated | 2026-03-27 |
| Owners | lotus-core query-service maintainers |
| Depends On | RFC 035, RFC 057, RFC 067, RFC 068 |
| Scope | Gold-standard PB/WM query APIs for portfolio discovery, transaction ledgers, AUM, asset allocation, cash balances, income summaries, and activity summaries |

## Executive Summary

This RFC introduces a coherent PB/WM query family in `lotus-core` `query_service`.
The implementation delivers:

1. An enhanced portfolio discovery API with explicit portfolio-list and business-unit scope support.
2. An enhanced transactions ledger API with requested-date-range filtering, optional `instrument_id`,
   and richer cost/trade analytics.
3. A typed wealth-reporting contract family for:
   - assets under management
   - asset allocation
   - cash balances
   - income summaries
   - activity summaries
4. Performance-aware query design using bounded scope semantics, latest-snapshot resolution, FX caching,
   and new query-hotspot indexes.

Classification: `Fully implemented and aligned`.

## Original Requested Requirements (Preserved)

The requested scope for this RFC family was:

1. Transactions API
   - portfolio-scoped
   - requested date range
   - optional `instrumentId`
   - all transaction attributes and analytics needed by UI and reporting
2. AUM API
   - support single portfolio, portfolio list, and BU level
   - support `as_of_date` and `reporting_currency`
3. Asset Allocation API
   - support dimensions such as asset class, currency, sector, country, and other available
     classifications
4. Portfolio API enhancement
   - publish all relevant portfolio attributes
   - support BU-level queries
5. Cash Balance API
   - portfolio-scoped cash accounts and totals
   - account balances in account, portfolio, and reporting currency
   - totals in portfolio and reporting currency
   - support `as_of_date` and optional `reporting_currency`
6. Architectural decision on whether AUM and cash should be combined
7. Income Summary API
   - support single portfolio, portfolio list, and BU scope
   - requested date range plus year-to-date view
   - values in portfolio currency and reporting currency
8. Activity Summary API
   - portfolio-level flow buckets
   - inflows, outflows, fees, taxes
   - requested date range plus year-to-date view
   - values in portfolio currency and reporting currency

## Architecture Decision

### Keep AUM and Cash Balance Separate

The implemented design keeps AUM and cash balances as separate APIs.

Reasoning:

1. AUM is a scope-level valuation aggregate.
2. Cash balance is a portfolio-level cash-account inventory and settlement view.
3. Combining them would mix:
   - aggregate valuation semantics
   - account-level operational cash semantics
4. The split makes contracts easier to use, easier to scale, and easier to evolve independently.

## Implemented API Surface

### Portfolio Discovery

- `GET /portfolios/`
- `GET /portfolios/{portfolio_id}`

Enhancements:

- `portfolio_ids` filter
- continued support for:
  - `portfolio_id`
  - `client_id`
  - `booking_center_code`
- portfolio record now includes `cost_basis_method`

This now supports:

- single-portfolio discovery
- explicit portfolio-list discovery
- BU-level discovery via `booking_center_code`

### Transactions Ledger

- `GET /portfolios/{portfolio_id}/transactions`

Enhancements:

- requested date range via `start_date` and `end_date`
- optional `instrument_id`
- richer response payload including:
  - `settlement_date`
  - `gross_cost`
  - `trade_fee`
  - `trade_currency`
  - detailed `costs`

This remains portfolio-scoped by design because transaction ownership and paging behavior are
operationally portfolio-centric.

### Wealth Reporting

- `POST /reporting/assets-under-management/query`
- `POST /reporting/asset-allocation/query`
- `POST /reporting/cash-balances/query`
- `POST /reporting/income-summary/query`
- `POST /reporting/activity-summary/query`

Request scope model:

- `portfolio_id`
- `portfolio_ids`
- `booking_center_code`

Currency rules:

1. Single portfolio:
   - reporting currency defaults to portfolio currency
2. Portfolio list or BU:
   - reporting currency is required

Asset allocation dimensions:

- `asset_class`
- `currency`
- `sector`
- `country`
- `product_type`
- `rating`
- `issuer_id`
- `issuer_name`
- `ultimate_parent_issuer_id`
- `ultimate_parent_issuer_name`

Cash-balance semantics:

- portfolio-scoped only
- returns native account balances, portfolio-currency balances, and reporting-currency balances
- returns totals in both portfolio and reporting currency

Income-summary semantics:

- supports `portfolio_id`, `portfolio_ids`, and `booking_center_code` scope
- accepts `window.start_date` and `window.end_date`
- returns:
  - requested-window totals
  - year-to-date totals through `window.end_date`
- covers canonical Lotus income types:
  - `DIVIDEND`
  - `INTEREST`
  - `CASH_IN_LIEU`
- exposes:
  - gross income
  - withholding tax
  - other deductions
  - net income
  - transaction count
- returns reporting-currency totals for every scope
- returns portfolio-currency values for:
  - per-portfolio rows
  - single-portfolio scope totals

Activity-summary semantics:

- supports `portfolio_id`, `portfolio_ids`, and `booking_center_code` scope
- accepts `window.start_date` and `window.end_date`
- returns:
  - requested-window totals
  - year-to-date totals through `window.end_date`
- activity is modeled as portfolio-level flow buckets, not generic ledger volume
- buckets are:
  - `INFLOWS`
  - `OUTFLOWS`
  - `FEES`
  - `TAXES`
- `TAXES` includes both:
  - explicit tax transactions
  - withholding-tax deductions from income transactions
- returns reporting-currency totals for every scope
- returns portfolio-currency values for:
  - per-portfolio rows
  - single-portfolio scope totals

## Performance Design

The implementation was designed for interactive PB/WM use, not naive unbounded scans.

### Transactions

1. Portfolio-scoped path keeps the read bounded.
2. Date filters use datetime ranges rather than `date(column)` wrapping so indexes remain usable.
3. New indexes support hot filters:
   - `ix_transactions_portfolio_instrument_date`
   - `ix_transactions_portfolio_settlement_cash_instrument_date`

### Reporting

1. Reporting queries resolve the latest non-zero snapshot per `(portfolio_id, security_id)` as of the
   requested date.
2. Snapshot selection is handled in SQL via window functions.
3. Only current-epoch state is used.
4. FX conversion is cached per request in the service layer.
5. BU and portfolio-list reporting stays scope-bounded through explicit scope resolution.
6. Income and activity summaries aggregate in SQL over bounded transaction-date windows rather than
   materializing raw ledger rows into Python.
7. Additional hot-path indexes support portfolio/date/type filters for income and flow summaries.

This is appropriate for:

- UI dashboards
- advisor workspaces
- reporting packs at portfolio and moderate BU scope

Large-scale extracts should use asynchronous export contracts rather than overloading interactive APIs.

## Evidence

Implementation:

- `src/services/query_service/app/routers/portfolios.py`
- `src/services/query_service/app/routers/transactions.py`
- `src/services/query_service/app/routers/reporting.py`
- `src/services/query_service/app/services/portfolio_service.py`
- `src/services/query_service/app/services/transaction_service.py`
- `src/services/query_service/app/services/reporting_service.py`
- `src/services/query_service/app/repositories/portfolio_repository.py`
- `src/services/query_service/app/repositories/transaction_repository.py`
- `src/services/query_service/app/repositories/reporting_repository.py`
- `src/services/query_service/app/repositories/date_filters.py`
- `src/services/query_service/app/dtos/portfolio_dto.py`
- `src/services/query_service/app/dtos/transaction_dto.py`
- `src/services/query_service/app/dtos/reporting_dto.py`
- `src/libs/portfolio-common/portfolio_common/database_models.py`
- `alembic/versions/a7c8d9e0f1a2_perf_add_wealth_query_indexes.py`
- `alembic/versions/b8d9e0f1a2b3_perf_add_income_activity_reporting_indexes.py`

Docs:

- `docs/features/query_service/WEALTH-REPORTING-API-GUIDE.md`
- `README.md`

Validation:

- `tests/unit/services/query_service/dtos/test_reporting_dto.py`
- `tests/unit/services/query_service/repositories/test_reporting_repository.py`
- `tests/unit/services/query_service/repositories/test_transaction_repository.py`
- `tests/unit/services/query_service/repositories/test_query_portfolio_repository.py`
- `tests/unit/services/query_service/services/test_reporting_service.py`
- `tests/unit/services/query_service/services/test_transaction_service.py`
- `tests/unit/services/query_service/services/test_portfolio_service.py`
- `tests/integration/services/query_service/test_reporting_router.py`
- `tests/integration/services/query_service/test_transactions_router.py`
- `tests/integration/services/query_service/test_portfolios_router_dependency.py`
- `tests/integration/services/query_service/test_main_app.py`

## Requirement-to-Implementation Traceability

| Requirement | Implementation | Evidence |
| --- | --- | --- |
| Portfolio-level transaction API with date range and optional instrument filter | Implemented | transactions router/service/repository + tests |
| Rich transaction attributes for UI/reporting | Implemented | transaction DTO + service mapping + tests |
| AUM query for portfolio, portfolio list, BU | Implemented | reporting DTO/service/router |
| Asset allocation by PB/WM dimensions | Implemented | allocation DTO/service |
| Portfolio API supports BU and explicit portfolio list | Implemented | portfolios router/service/repository |
| Cash balances with native/portfolio/reporting currency | Implemented | cash balances DTO/service/router |
| Income summary with requested-window and YTD currency views | Implemented | reporting DTO/service/repository/router + tests |
| Activity summary with portfolio-level flow buckets and YTD currency views | Implemented | reporting DTO/service/repository/router + tests |
| Performance-aware design | Implemented | date-range predicates, latest-snapshot query, hot-path indexes, tests |

## Validation Summary

The implementation passed:

1. Focused touched-surface lint.
2. Focused query-service contract pack:
   - `82 passed`
3. Full query-service unit suite:
   - `468 passed`
4. Full query-service integration suite:
   - `90 passed`
5. Focused income/activity reporting contract pack:
   - `83 passed`

Alembic head is clean with the new migration registered.

## Open Questions

1. Should a future async reporting-export contract share the same DTO vocabulary as the interactive
   reporting APIs or define export-specific envelope metadata?
2. Should BU scope later broaden beyond `booking_center_code` into an explicit enterprise business-unit
   hierarchy contract?

## Next Actions

1. Keep this RFC as the active authority for PB/WM read-model and reporting query behavior in
   `lotus-core`.
2. Preserve the requested-window plus year-to-date summary pattern for future source-data summary
   contracts so UI and reporting consumers do not need to rebuild the same logic client-side.
3. If downstream consumers require bulk export at larger BU scale, add an asynchronous export contract
   rather than broadening the interactive query endpoints.
