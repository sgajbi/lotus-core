# Front-Office Portfolio Seed Runbook

This runbook seeds one realistic discretionary portfolio scenario for local
gateway and UI development, plus two source-only DPM universe candidate rows
used to prove bounded Core candidate discovery.

Use this when you need one portfolio that exercises:

- portfolio context
- holdings
- transactions
- allocation
- cash balances
- income summary
- activity summary
- benchmark-linked performance
- forward projected cashflow
- DPM source-owner client restrictions and sustainability preferences

This runbook is local-only and does not depend on `lotus-manage`.

Routine front-office analytics seeding is intentionally limited to `PB_SG_GLOBAL_BAL_001`. The
seed also publishes source-only candidate portfolio master and mandate-binding rows for
`PB_SG_GLOBAL_INC_002` and `PB_SG_GLOBAL_GROWTH_003` so `DpmPortfolioUniverseCandidate:v1` can prove
multi-candidate discovery and paging without pretending those portfolios are full holdings,
performance, risk, or Workbench demo portfolios. The governed RFC-086 bank-day load scenario with
`1000` portfolios is separate load/performance tooling and is not part of canonical Workbench
runtime bring-up.

## Seeded Portfolio

- portfolio id: `PB_SG_GLOBAL_BAL_001`
- client id: `CIF_SG_000184`
- booking centre: `Singapore`
- mandate: global balanced discretionary
- base currency: `USD`

## What This Seed Includes

- 10+ current positions
- USD and EUR cash accounts
- funded USD and EUR sleeves with no structural negative operating cash
- equities, funds, and fixed income
- 12 months of market prices and EUR/USD FX
- benchmark assignment and benchmark reference data
- discretionary mandate binding, model target, instrument eligibility, tax-lot, market-data,
  client-restriction, and sustainability-preference source records for DPM assembly proof
- income, fee, tax, sell, and withdrawal activity
- two future/planned withdrawals covering both the canonical and current forward cashflow horizons
- planned settlement dates are rolled to business days and backed by FX coverage
  through the latest projected settlement date
- canonical paired product-and-cash transactions aligned with the core demo ingest pattern
- normalized cash-book transaction rows with `price = 1` and
  `quantity = gross_transaction_amount`
- full valuation coverage through the report end date so performance analytics remain valid
- FX and benchmark component coverage through the forward validation window so
  next-day and current-date analytics requests remain valid. The seed extends these reference
  series through at least 45 calendar days after the canonical as-of date, and through any later
  projected settlement date.
- the current raw `market_prices` and `fx_rates` contracts are point-in-time
  series; a future effective-range schema should represent open-ended terminal
  price/rate validity with `3999-12-31`, not with ambiguous missing end dates
- client restriction records for:
  - private-credit buys blocked by `NO_PRIVATE_CREDIT_BUY`
  - sanctioned-market buys blocked by `NO_SANCTIONED_MARKET_BUY`
- sustainability preference records for:
  - minimum sustainable allocation `0.2000000000`
  - thermal-coal exclusion `THERMAL_COAL`
  - low-carbon-transition positive tilt `LOW_CARBON_TRANSITION`
- DPM portfolio-universe source-only candidate rows for:
  - `PB_SG_GLOBAL_INC_002` / `MANDATE_PB_SG_GLOBAL_INC_002`
  - `PB_SG_GLOBAL_GROWTH_003` / `MANDATE_PB_SG_GLOBAL_GROWTH_003`

## Operator Command

Run from the `lotus-core` repo root:

```powershell
python tools/front_office_portfolio_seed.py `
  --portfolio-id PB_SG_GLOBAL_BAL_001 `
  --start-date 2025-03-31 `
  --end-date 2026-04-10 `
  --benchmark-start-date 2025-01-06 `
  --wait-seconds 300
```

## Validation Performed By The Tool

The tool ingests the portfolio bundle plus benchmark reference data and then
verifies:

- required cross-currency FX windows are queryable before transaction replay
- positions are populated
- valued positions are populated
- transactions are populated
- cash accounts are populated
- allocation views are populated
- income summary is populated
- activity summary is populated
- projected cashflow contains at least one non-zero future point
- benchmark assignment resolves
- DPM client restriction and sustainability preference source records resolve through
  query-control-plane integration routes
- DPM portfolio-universe candidates return the governed three-candidate source scenario and prove
  continuation-token paging
- gateway performance summary resolves with benchmark-linked content
- core analytics reference `performance_end_date` is at or after the seed end date and represents
  a complete calculable performance horizon across portfolio and position analytics source
  families
- gateway performance `report_end_date` and return-path latest available date are
  at or after the seed end date

## Validation Evidence

The current seeded scenario was validated directly against the local stack after
the RFC-0075 Slice 4 derived-state readiness fix with these outcomes:

- `lotus-core query_service`
  - positions: `11`
  - valued positions: `11`
  - transactions: `31`, including future/planned transactions
    `TXN-WITHDRAWAL-FUTURE-001` and `TXN-WITHDRAWAL-CURRENT-HORIZON-001`
  - cash accounts: `2`
  - cashflow projection: `31` points with non-zero planned withdrawal points on
    `2026-04-17` for `-18000` and `2026-04-30` for `-12000`
  - allocation views: `asset_class`, `sector`, `region`, `currency`
  - market price coverage through `2026-04-10`
  - EUR/USD FX and benchmark return coverage through `2026-05-25`
  - USD risk-free coverage through `2026-05-10`
  - no `PORT_SMOKE_%` portfolio rows remained after the clean seed
- `lotus-core query_control_plane`
  - benchmark assignment resolves to `BMK_PB_GLOBAL_BALANCED_60_40`
  - analytics reference `performance_end_date` resolves to `2026-04-10`, the latest complete
    performance horizon usable by downstream TWR
  - DPM source products resolve client restriction and sustainability preference records for
    `PB_SG_GLOBAL_BAL_001` when the RFC40-WTBD-008 source-owner slice is applied
  - DPM portfolio-universe candidate discovery returns `PB_SG_GLOBAL_BAL_001`,
    `PB_SG_GLOBAL_INC_002`, and `PB_SG_GLOBAL_GROWTH_003` as Core-owned candidate rows; this proves
    source-owned candidate discovery only. The live DPM source validator also follows the
    continuation token from a one-row candidate page and rejects duplicate or empty continuation
    pages. This does not prove relationship householding, suitability, PM ranking, execution
    readiness, client workflow, or full analytics support for the source-only rows.
- `lotus-core portfolio_aggregation_service`
  - portfolio aggregation backlog for `PB_SG_GLOBAL_BAL_001`: `0` pending,
    `0` processing, `382` complete
  - portfolio timeseries max date: `2026-04-17`
- `lotus-gateway`
  - performance and risk summary endpoints return `200`
  - performance summary `report_end_date`: `2026-04-11`
  - return-path `latest_available_date`: `2026-04-11`

If the seed verifier times out after positions and position timeseries are
available, check `portfolio_aggregation_jobs` for a pending backlog and
`portfolio_timeseries` for a stale max date. The canonical readiness path
requires portfolio aggregation to catch up before workbench validation or demo
screenshots are accepted.

The seed cleanup remains bounded to `PB_SG_GLOBAL_BAL_001` data plus known volatile replay fences
for canonical seed topics. It clears stale local `processed_events` fences that can survive when
Kafka offsets are reset or reused, but it must not delete unrelated processed-event history or broad
runtime tables.

If a prior local load or performance run polluted broader shared `lotus-core` Docker state, reset
the Docker-backed core runtime before reseeding instead of broadening the seed cleanup SQL. The
governed Workbench startup script accepts `-CleanCoreState` for this purpose.

## Related Documents

- seed contract:
  - [Front-Office-Portfolio-Seed-Contract.md](/C:/Users/Sandeep/projects/lotus-core/docs/operations/Front-Office-Portfolio-Seed-Contract.md)
- benchmark repair seed:
  - [Manual-Portfolio-Performance-Benchmark-Seed-Runbook.md](/C:/Users/Sandeep/projects/lotus-core/docs/operations/Manual-Portfolio-Performance-Benchmark-Seed-Runbook.md)
- tool:
  - [front_office_portfolio_seed.py](/C:/Users/Sandeep/projects/lotus-core/tools/front_office_portfolio_seed.py)
