# Front-Office Portfolio Seed Runbook

This runbook seeds one realistic discretionary portfolio scenario for local
gateway and UI development.

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

This runbook is local-only and does not depend on `lotus-manage`.

Routine front-office seeding is intentionally limited to `PB_SG_GLOBAL_BAL_001`. The governed
RFC-086 bank-day load scenario with `1000` portfolios is separate load/performance tooling and is
not part of canonical Workbench runtime bring-up.

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
- income, fee, tax, sell, and withdrawal activity
- one future-dated withdrawal inside the forward cashflow horizon
- canonical paired product-and-cash transactions aligned with the core demo ingest pattern
- normalized cash-book transaction rows with `price = 1` and
  `quantity = gross_transaction_amount`
- full valuation coverage through the report end date so performance analytics remain valid
- FX and benchmark component coverage through the forward validation window so
  next-day analytics requests remain valid

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
- gateway performance summary resolves with benchmark-linked content
- core analytics reference `performance_end_date` is at or after the seed end date
- gateway performance `report_end_date` and return-path latest available date are
  at or after the seed end date

## Validation Evidence

The current seeded scenario was validated directly against the local stack after
the RFC-0075 Slice 4 derived-state readiness fix with these outcomes:

- `lotus-core query_service`
  - positions: `11`
  - valued positions: `11`
  - transactions: `30`, including future transaction
    `TXN-WITHDRAWAL-FUTURE-001`
  - cash accounts: `2`
  - cashflow projection: `31` points with one non-zero point on `2026-04-17`
    for `-18000`
  - allocation views: `asset_class`, `sector`, `region`, `currency`
  - market price coverage through `2026-04-10`
  - EUR/USD FX, benchmark return, and USD risk-free coverage through `2026-05-10`
  - no `PORT_SMOKE_%` portfolio rows remained after the clean seed
- `lotus-core query_control_plane`
  - benchmark assignment resolves to `BMK_PB_GLOBAL_BALANCED_60_40`
  - analytics reference `performance_end_date` resolves to `2026-04-10`
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

If a prior local load or performance run polluted shared `lotus-core` Docker state, reset the
Docker-backed core runtime before reseeding instead of broadening the seed cleanup SQL. The
governed Workbench startup script accepts `-CleanCoreState` for this purpose.

## Related Documents

- seed contract:
  - [Front-Office-Portfolio-Seed-Contract.md](/C:/Users/Sandeep/projects/lotus-core/docs/operations/Front-Office-Portfolio-Seed-Contract.md)
- benchmark repair seed:
  - [Manual-Portfolio-Performance-Benchmark-Seed-Runbook.md](/C:/Users/Sandeep/projects/lotus-core/docs/operations/Manual-Portfolio-Performance-Benchmark-Seed-Runbook.md)
- tool:
  - [front_office_portfolio_seed.py](/C:/Users/Sandeep/projects/lotus-core/tools/front_office_portfolio_seed.py)
