# Front-Office Portfolio Seed Contract

This document defines the target local seed scenario that should be implemented
in `lotus-core` so gateway and UI teams can build against one realistic,
feature-complete portfolio instead of a narrow benchmark-only seed.

This is not a generic demo pack requirement. It is a product-development seed
contract for a single high-value front-office workstation example.

## Objective

Create one realistic discretionary private-banking portfolio seed that can
surface the majority of current `lotus-core`, `lotus-performance`, gateway, and
UI features without depending on fake placeholder states.

The seed must support:

- summary-first portfolio workspace
- holdings and transaction drill-down
- allocation views
- liquidity and projected cashflow
- readiness and exception handling
- benchmark-linked performance summary
- benchmark-linked performance analysis
- performance evidence expansion later
- DPM source-owner proof for mandate restrictions and sustainability preferences

## Seed Design Principles

- one real portfolio scenario is better than many shallow demos
- data should be business-coherent, not just API-complete
- each seeded module must support at least one real UI action or drill-down
- exceptions must be intentional and explainable, not random corruption
- the seed must be rerunnable and deterministic in local development
- the seed must not require `lotus-manage`

## Recommended Reference Scenario

Use one discretionary multi-asset relationship-book portfolio with:

- base currency: `USD`
- client domicile / booking context outside the US
- multi-currency holdings and cash
- benchmark assignment
- funded cash balances
- income-producing assets
- fixed income with accrual behavior
- recent activity across multiple transaction types
- full valuation coverage through the active analysis window

Recommended example:

- portfolio id: `PB_SG_GLOBAL_BAL_001`
- client id: `CIF_SG_000184`
- portfolio display name: `Global Balanced Mandate`
- client display name: `Anjali Raman`
- relationship manager id: `RM_SG_001`
- booking centre: `Singapore`
- strategy: global balanced discretionary mandate
- portfolio type: `Discretionary`

## Minimum Product Surface Coverage

The seed must make the following product surfaces materially usable.

### Portfolio context and overview

- portfolio identity
- client identity
- booking setup
- base/reporting currency
- opened date
- relationship manager

### Holdings and valuation

- at least 10 current positions
- mix of:
  - cash
  - equities
  - funds
  - fixed income
- non-zero valuations
- multi-currency valuations translated into reporting currency
- current holdings must all remain valued through the active analysis window
- use proper security identifiers and proper display names, not placeholder
  `MANUAL_*` or `SEC_*` codes in the front-office seed

### Allocation

- asset class allocation
- sector allocation
- region allocation
- currency allocation
- enough instrument metadata to make allocation filters meaningful

### Transactions and activity

- at least 25-40 transactions across the portfolio lifecycle
- transaction types should include:
  - cash funding / inflow
  - buys
  - sells
  - dividend
  - interest
  - fee
  - tax / withholding
  - FX-related funding or cross-currency settlement where relevant
- transactions should cover both historical onboarding and recent activity
- at least one recent transaction window should power activity summaries

### Income

- dividend income
- coupon / interest income
- deductions or withholding on at least one income event
- net and gross income should differ for at least one event

### Liquidity and cashflow

- multiple cash accounts
- projected cash movements over both the canonical contract window and the current Workbench
  forward-liquidity horizon
- future-dated settlement activity or projected cash events
- benchmark and FX coverage through the forward validation horizon so next-day
  analytics requests do not fail on missing reference data
- enough data to show:
  - current available cash
  - cash by currency
  - projected net flow
  - end-of-window liquidity

### Performance and benchmark

- benchmark assignment effective before portfolio open date or before the
  analysis window starts
- daily price history for all relevant securities
- daily FX for all required currency pairs
- portfolio timeseries coverage across:
  - 7D
  - 30D
  - MTD
  - QTD
  - YTD
  - 1Y when enough synthetic history exists
- benchmark-linked summary:
  - portfolio return
  - benchmark return
  - active return
  - money-weighted return
- canonical benchmark component classifications:
  - `IDX_GLOBAL_EQUITY_TR` uses `sector=broad_market_equity`
  - `IDX_GLOBAL_BOND_TR` uses `sector=broad_market_fixed_income`
  - these broad-market sector labels are source-owned inputs for downstream
    benchmark exposure grouping; downstream services should not infer sector
    labels for canonical benchmark components
- analysis detail:
  - return path chart
  - multi-horizon panel
  - contributors
  - attribution

### Exceptions and readiness

This canonical portfolio seed must remain analytically usable end to end.

Do not introduce stale-price or missing-price conditions into the primary
portfolio seed if they would cap `performance_end_date` or distort benchmark,
contribution, or attribution outputs.

If readiness/error flows need explicit coverage, seed them in a separate
operator scenario rather than degrading the primary front-office reference
portfolio.

## Data Shape Requirements

### Instrument metadata

Each non-cash instrument should have enough metadata to support:

- asset class
- sector
- region / country
- instrument type
- currency
- issuer or security name
- benchmark attribution group where relevant

The seed should use proper business labels, for example:

- `asset_class`
  - `Equity`
  - `Fixed Income`
  - `Fund`
  - `Cash`
- `sector`
  - `Information Technology`
  - `Government`
  - `Multi-Asset`
  - `Financials`
- `region`
  - `North America`
  - `Europe`
  - `Global`
- `country_of_risk`
  - `United States`
  - `Germany`
  - `Ireland`
  - `Netherlands`
- `issuer_name`
  - `Apple Inc.`
  - `Microsoft Corporation`
  - `United States Treasury`
  - `BlackRock`
  - `PIMCO`
  - `Siemens Financieringsmaatschappij NV`

Avoid placeholder values such as:

- `MANUAL_*`
- `SEC_*`
- `FUND_1`
- `BOND_A`
- generic lower-quality labels like `global` when the business label should be
  `Global`

Recommended seeded current universe:

- `CASH_USD_BOOK_OPERATING`
  - display name: `USD Operating Cash`
- `CASH_EUR_BOOK_OPERATING`
  - display name: `EUR Operating Cash`
- `US0378331005`
  - display name: `Apple Inc.`
- `US5949181045`
  - display name: `Microsoft Corporation`
- `DE0007164600`
  - display name: `SAP SE`
- `IE00B4L5Y983`
  - display name: `iShares Core MSCI World UCITS ETF`
- `LU0171301533`
  - display name: `BlackRock Global Allocation Fund`
- `IE00B11XZ103`
  - display name: `PIMCO GIS Income Fund`
- `US91282CHP95`
  - display name: `United States Treasury 3.875% 2030`
- `XS2671347285`
  - display name: `Siemens Financieringsmaatschappij NV 2.500% 2031`
- `Private Credit Opportunities Fund A`

### History depth

The current manual seed is too short for a realistic performance workstation.

Target minimum history depth:

- prices and FX: 12 months
- benchmark series: 12 months
- transactions: at least 3-6 months of realistic activity
- FX and benchmark component/reference coverage should extend through the active
  forward cashflow validation horizon, not stop exactly at the report end date

That does not require 12 months of dense transaction flow. It does require
enough historical market series to make the performance periods meaningful.

### Cross-currency coverage

At minimum support:

- USD
- EUR

The preferred seed shape is:

- base currency: USD
- reporting currencies exercised: USD and EUR
- holdings currencies: USD and EUR
- optional third-currency exposure only if it drives a real product feature
  under active development

If the portfolio keeps the current Singapore context, use that as booking and
client context, not as a reason to add unnecessary FX complexity.

## Transaction Semantics

The seeded transactions should use meaningful business semantics and labels.

Recommended transaction storyline:

- initial funding into USD operating cash
- staged deployment into:
  - US equities
  - global allocation fund
  - income fund
  - sovereign bond
  - corporate bond
- one partial trim / profit-taking sale
- one dividend receipt
- one coupon or interest receipt
- one advisory or custody fee
- one withholding-tax event
- future-dated settlement or projected cash events that keep both canonical and current
  forward-liquidity windows non-empty

Each transaction should carry meaningful values for all attributes that affect
downstream surfaces, including where supported:

- transaction type
- trade date
- settlement date
- trade currency
- gross amount
- quantity
- price
- fees
- taxes / withholding
- narrative or reference

A cash-book transaction row in this seed must use one normalized operating-cash
shape:

- `security_id` is the cash instrument
- `price = 1`
- `quantity = gross_transaction_amount`
- `currency = trade_currency`

Avoid ambiguous paired fake cash rows if a clearer cash-movement contract is
available in the current ingest model.

## Required Downstream Behaviors

The seed is acceptable only if it supports these behaviors end to end.

### Portfolio workspace

- summary KPIs are populated
- holdings grid is populated
- top holdings is populated
- allocation is populated
- activity summary is populated
- income summary is populated
- projected cashflow is populated
- readiness shows either zero or a small intentional number of explainable
  exceptions
- DPM source routes expose the mandate binding, model targets, instrument eligibility, tax lots,
  market-data coverage, client restrictions, and sustainability preferences needed by downstream
  stateful portfolio-construction proof

### Drill-downs

- clicking a holding can resolve related transactions
- clicking an activity bucket returns a filtered transaction set
- clicking an allocation bucket returns a filtered holdings set
- clicking readiness exceptions resolves the affected securities or holdings set

### Performance workspace

- summary mode is populated
- analysis mode is populated
- evidence mode may still be placeholder, but the underlying calculation and
  lineage-ready fields should not be structurally blocked by missing benchmark
  data

## Non-Goals

This seed does not need to simulate every future feature.

It does not need:

- proposal generation
- suitability
- recommendation engine outputs
- `lotus-manage` workflows or rebalance decisioning
- every possible transaction type in the platform

It does need to cover the current gateway/UI build path honestly and
meaningfully.

## Implementation Recommendation

Implement this as a new dedicated seed tool in `lotus-core`, separate from the
current narrow benchmark patch tool.

Recommended shape:

- keep `tools/manual_performance_seed.py` as the focused benchmark-repair tool
- add a new tool for the broader scenario, for example:
  - `tools/front_office_portfolio_seed.py`

That tool should:

1. seed or refresh the portfolio master and context
2. seed instruments with classification coverage
3. seed historical transactions
4. seed prices and FX with enough history depth
5. seed benchmark definitions, compositions, return series, and assignments
6. seed DPM source-owner records for mandate binding, model targets, eligibility, tax lots,
   market-data coverage, client restrictions, and sustainability preferences
7. wait for downstream calculators
8. run a governed validation checklist across core, performance, gateway, and source-product
   routes

## Validation Contract

The future seed tool should validate at least:

- positions non-empty
- cash balances non-empty
- transactions non-empty
- allocation views non-empty
- income summary non-empty
- activity summary non-empty
- projected cashflow non-empty
- benchmark assignment non-empty
- client restriction profile non-empty
- sustainability preference profile non-empty
- portfolio timeseries non-empty
- gateway performance summary non-empty
- gateway performance details non-empty

## Current Gap

Today we have:

- a manual portfolio bootstrap
- a separate manual benchmark/performance patch seed

That is enough to unblock narrow UI development, but not enough to provide one
realistic front-office example covering the product surface coherently.

This contract exists to close that gap with one governed seed scenario rather
than more ad hoc local fixes.
