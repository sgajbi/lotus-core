# Wealth Reporting API Guide

## Purpose

This guide documents the gold-standard PB/WM reporting APIs exposed by `lotus-core`
`query_service`. The API family is designed for:

- UI portfolio workspaces
- reporting packs and scheduled extracts
- downstream wealth applications that need consistent Lotus query contracts

The design goal is to keep canonical ledger and discovery reads simple while giving
wealth-reporting use cases stronger, typed contracts.

This guide also covers the portfolio-workspace follow-up contracts that make historical
portfolio workspaces trustworthy for PB/WM consumers:

- canonical cash-account master ingestion and query
- true historical as-of portfolio summary and holdings snapshot contracts
- reporting-currency restatement for portfolio workspace modules
- region and look-through allocation support

## API Surface

### Portfolio discovery

- `GET /portfolios/`
- `GET /portfolios/{portfolio_id}`

Use this family for portfolio discovery, navigation, and attribute retrieval.

Supported filters:

- `portfolio_id`
- `portfolio_ids`
- `client_id`
- `booking_center_code`

This means the portfolio API now supports:

- single-portfolio queries
- explicit portfolio-list queries
- business-unit queries through `booking_center_code`

### Transactions

- `GET /portfolios/{portfolio_id}/transactions`

This remains a portfolio-scoped ledger API because that matches the domain:

- transaction history is operationally owned at portfolio level
- consumers usually need paging, sorting, and timeline filters rather than wide-scope aggregation

Supported filters include:

- requested date range via `start_date` and `end_date`
- `instrument_id`
- `security_id`
- canonical transaction typing fields
- FX lifecycle filters

The response includes both canonical transaction attributes and reporting-relevant analytics such as:

- transaction date and settlement date
- gross cost
- trade fee
- trade currency
- linked cashflow details
- detailed transaction costs

Security drill-down behavior:

- use `security_id` to retrieve the transaction history for a specific holding inside the
  portfolio
- this is the source-backed contract for holdings workspace drill-down and "latest transaction for
  this security" use cases
- when callers do not override sorting, results are returned latest-first using
  `transaction_date DESC`

Settlement-date semantics:

- `transaction_date` is the booked ledger date/time
- `settlement_date` is the canonical contractual or effective settlement timestamp when available
- downstream UI and reporting consumers should use the source-owned `settlement_date` directly
  rather than inferring settlement timing from cash legs or transaction type

### Cash account master

- `GET /portfolios/{portfolio_id}/cash-accounts`

Use this contract for canonical cash-account identity and lifecycle metadata.

Inputs:

- `portfolio_id`
- optional `as_of_date`

Behavior:

- returns source-owned cash-account master rows
- filters accounts by `opened_on` / `closed_on` when `as_of_date` is provided
- does not infer account identity from transactions

This is the master-data contract that reporting cash-balance queries build on top of.

## Why AUM and Cash Balances Are Separate

We keep AUM and cash balances as separate APIs because they serve different domain models.

### AUM

AUM is a valuation aggregate. It answers:

- what is the market value of this scope as of a date?

This works naturally across:

- one portfolio
- a portfolio list
- a business unit

### Cash balances

Cash balance is an account-level cash inventory view. It answers:

- which cash accounts exist in a portfolio?
- what are their balances by native, portfolio, and reporting currency?

This is naturally portfolio-scoped because cash account identity and settlement mappings are
owned at portfolio level.

Combining these APIs would blur two different concepts:

- aggregate valuation
- account-level operational cash

The split keeps the contracts easier to reason about and easier to scale.

## Reporting APIs

### Assets Under Management

- `POST /reporting/assets-under-management/query`

Request scope:

- `portfolio_id`
- `portfolio_ids`
- `booking_center_code`

Inputs:

- `as_of_date`
- `reporting_currency`

Behavior:

- for single-portfolio scope, `reporting_currency` defaults to portfolio currency
- for portfolio-list and business-unit scopes, `reporting_currency` is required

Response highlights:

- scope echo and resolved scope type
- resolved as-of date
- effective reporting currency
- scope totals
- per-portfolio AUM breakdown

### Asset Allocation

- `POST /reporting/asset-allocation/query`

Request scope:

- `portfolio_id`
- `portfolio_ids`
- `booking_center_code`

Inputs:

- `as_of_date`
- `reporting_currency`
- `dimensions`

Supported dimensions:

- `asset_class`
- `currency`
- `sector`
- `country`
- `region`
- `product_type`
- `rating`
- `issuer_id`
- `issuer_name`
- `ultimate_parent_issuer_id`
- `ultimate_parent_issuer_name`

Look-through behavior:

- `look_through_mode = direct_only`
  - keep parent holdings intact
- `look_through_mode = prefer_look_through`
  - decompose eligible parent instruments when a fully weighted source-owned component set exists
  - preserve direct holdings for the remaining positions
  - return a `look_through` capability / limitation block in the response

Behavior:

- returns one allocation view per requested dimension
- every bucket includes reporting-currency market value, weight, and position count
- region is derived from country-of-risk using the source-owned Lotus classification helper

### Portfolio Summary

- `POST /reporting/portfolio-summary/query`

Inputs:

- `portfolio_id`
- `as_of_date`
- optional `reporting_currency`

Behavior:

- returns a true historical as-of portfolio snapshot summary
- returns totals in:
  - portfolio currency
  - reporting currency
- separates:
  - total market value
  - cash balance
  - invested market value
- returns snapshot metadata including:
  - resolved snapshot date
  - position count
  - cash-account count
  - valued / unvalued counts

### Holdings Snapshot

- `POST /reporting/holdings-snapshot/query`

Inputs:

- `portfolio_id`
- `as_of_date`
- optional `reporting_currency`
- `include_cash_positions`

Behavior:

- returns a true historical as-of holdings snapshot
- returns each holding in:
  - portfolio currency
  - reporting currency
- returns portfolio-workspace classifications including:
  - asset class
  - sector
  - country
  - region
- supports excluding cash positions for pure investment holdings views

### Cash Balances

- `POST /reporting/cash-balances/query`

Inputs:

- `portfolio_id`
- `as_of_date`
- optional `reporting_currency`

Behavior:

- defaults `reporting_currency` to portfolio currency
- resolves accounts from canonical cash-account master data first
- falls back to latest settlement-cash transaction linkage only when no master row exists
- returns each cash account in:
  - account currency
  - portfolio currency
  - reporting currency
- returns portfolio totals in:
  - portfolio currency
  - reporting currency
- includes zero-balance master accounts so the workspace sees the full account inventory

If no explicit account master or linkage is available, the API falls back to the cash instrument
identity as the last-resort identifier.

### Income Summary

- `POST /reporting/income-summary/query`

Inputs:

- scope:
  - `portfolio_id`
  - `portfolio_ids`
  - `booking_center_code`
- `window.start_date`
- `window.end_date`
- optional `reporting_currency`
- optional `income_types`

Behavior:

- returns two views for every response:
  - requested window
  - year to date through `window.end_date`
- preserves portfolio-currency values for per-portfolio rows
- translates every result into the effective reporting currency
- summarizes canonical Lotus income types:
  - `DIVIDEND`
  - `INTEREST`
  - `CASH_IN_LIEU`

Income totals expose:

- gross income
- withholding tax
- other deductions
- net income
- transaction count

### Activity Summary

- `POST /reporting/activity-summary/query`

Inputs:

- scope:
  - `portfolio_id`
  - `portfolio_ids`
  - `booking_center_code`
- `window.start_date`
- `window.end_date`
- optional `reporting_currency`

Behavior:

- returns two views for every response:
  - requested window
  - year to date through `window.end_date`
- activity is intentionally modeled as portfolio-level flow buckets, not general ledger volume
- current buckets are:
  - `INFLOWS`
  - `OUTFLOWS`
  - `FEES`
  - `TAXES`

Bucket semantics:

- `INFLOWS`:
  - deposit and transfer-in cash activity
- `OUTFLOWS`:
  - withdrawal and transfer-out cash activity
- `FEES`:
  - fee transactions
- `TAXES`:
  - explicit tax transactions plus withholding-tax deductions captured on income records

All bucket values are returned in:

- portfolio currency for per-portfolio rows
- reporting currency for all results

## Performance Model

These APIs are designed around bounded, index-friendly reads rather than open-ended scans.

### Transactions API

The transactions ledger is optimized for UI and reporting pagination:

- portfolio-scoped path keeps the read bounded
- filters are applied before pagination
- date filtering uses datetime range predicates instead of `date(column)` wrapping so the
  transaction date indexes remain useful
- dedicated indexes support hot filters such as:
  - `(portfolio_id, instrument_id, transaction_date)`
  - `(portfolio_id, settlement_cash_instrument_id, transaction_date)`

This is the right model for transaction workflows. A streaming export can be added later for
very large reporting jobs without weakening the main ledger contract.

### Reporting APIs

The reporting APIs use the latest non-zero snapshot per `(portfolio_id, security_id)` as of the
requested date. This keeps the query bounded while preserving true historical as-of semantics.

Important characteristics:

- latest-snapshot resolution is handled in SQL with a window function
- historical queries are not pinned to current epoch only
- FX conversion is cached per request in the service layer
- scope-wide reporting is based on the resolved portfolio set instead of repeated per-portfolio
  round trips
- look-through decomposition is only applied when source-owned component weights form a complete set

This makes the APIs suitable for:

- interactive dashboards
- analyst drill-down
- reporting generation over moderate scope sizes

If very large BU exports are required later, that should be modeled as an asynchronous export
contract rather than overloading the interactive query APIs.

The income-summary and activity-summary APIs follow the same principle:

- bounded transaction-date windows
- SQL-side aggregation grouped by scope and currency
- request-scoped FX conversion caching
- composite indexes on `(portfolio_id, transaction_type, transaction_date)` for hot-path filters

## Design Principles

These APIs follow a few rules consistently:

- canonical discovery reads stay in `query_service`
- higher-order reporting uses typed `POST` contracts
- portfolio currency and reporting currency semantics are explicit
- true historical `as_of_date` semantics are explicit for snapshot-backed views
- scope resolution is part of the request contract, not implicit server behavior
- responses echo resolved dates and effective currencies
- canonical account identity comes from source-owned master data, not downstream inference

## Testing Standard

The supporting tests are intended to lock real domain behavior:

- DTO tests cover scope and currency rules
- service tests cover aggregation, FX conversion, historical snapshot behavior, look-through, and
  cash-account behavior
- repository tests cover SQL shape for scope filters, latest-snapshot resolution, and
  index-friendly date predicates
- integration tests cover FastAPI routing and OpenAPI contract visibility
