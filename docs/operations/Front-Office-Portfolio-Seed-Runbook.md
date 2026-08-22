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

The broad app-local `demo_data_loader` demo pack is also outside the canonical private-banking
seed. Governed Workbench and platform QA startup must run `lotus-core` with
`DEMO_DATA_PACK_ENABLED=false` so canonical `PB_SG_GLOBAL_BAL_001` evidence is produced only by
`tools/front_office_portfolio_seed.py` and the source-only DPM candidate rows described here.

## Seeded Portfolio

- portfolio id: `PB_SG_GLOBAL_BAL_001`
- valuation tenant id: `LOTUS_PB_SG`
- valuation legal book id: `SG_PRIVATE_BANK_BOOK`
- client id: `CIF_SG_000184` (cataloged synthetic seed identifier)
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
- unit-price cash authority through the latest planned-withdrawal transaction date so future cash
  legs do not create terminal exact-scope valuation failures
- effective-dated valuation-policy assignments for every seeded instrument and authoritative
  market-price source facts for every seeded price observation. The canonical source contract
  defines one held bond unit as 1,000 face and deterministically normalizes its clean-percent quote
  into `UNIT_PRICE`; all assignments therefore use `UNIT_PRICE_MARKET_VALUE` without treating
  position quantity as runtime face authority.
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
python scripts/development/repository_python.py tools/front_office_portfolio_seed.py `
  --portfolio-id PB_SG_GLOBAL_BAL_001 `
  --start-date 2025-03-31 `
  --end-date 2026-04-10 `
  --benchmark-start-date 2025-01-06 `
  --evidence-output output/front-office-qa/canonical-seed-verification.json `
  --wait-seconds 900
```

## Validation Performed By The Tool

The tool ingests the portfolio bundle plus benchmark reference data and then
verifies:

- required cross-currency FX windows are queryable before transaction replay
- policy assignments and authoritative price source facts are ingested after raw price readiness
  and before the business-date horizon activates
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
  full continuation-token paging through terminal page exhaustion; the complete READY response
  must carry a non-placeholder `sha256:` `content_hash` with an identical `source_digest`
- gateway performance summary resolves with benchmark-linked content
- core analytics reference `performance_end_date` is at or after the seed end date and represents
  a complete calculable performance horizon across portfolio and position analytics source
  families
- gateway performance `report_end_date` and return-path latest available date are
  at or after the seed end date
- three consecutive observations contain no pending, processing, stale, or failed valuation or
  aggregation work; any reopened scheduler work resets this non-amplification fence
- the optional evidence file is emitted only after an exact read-only PostgreSQL comparison of
  every seed-owned assignment and source fact; it derives durable counts and hashes from those
  rows and binds them with governed dates, terminal queue observations, and the final verification
  result using a SHA-256 content hash

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
    source-owned candidate discovery only. The live DPM source validator also walks one-row
    candidate pages until the terminal page, requires every governed candidate to appear exactly
    once, rejects duplicate, empty, or non-terminating continuation pages, and rejects a complete
    READY response without Core-owned canonical content identity. `source_batch_fingerprint`
    remains null unless persisted upstream batch evidence exists. This does not prove
    relationship householding, suitability, PM ranking, execution readiness, client workflow, or
    full analytics support for the source-only rows.
- `lotus-core portfolio_derived_state_service`
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

If only the fixed-income positions remain unvalued, inspect `portfolio_valuation_jobs` before
retrying. `bond valuation requires explicit quote-convention authority` means the canonical
policy assignment or same-tenant/same-book authoritative source fact is missing; it must not be
worked around with the retired magnitude heuristic or a downstream-fabricated quote basis. The
tool waits for the exact canonical portfolio tenant/book scope to become durable before publishing
dependent instruments, authority, business dates, or transactions, including on a full reseed of
an older portfolio row. The
routine seed cleanup never removes this shared tenant/book/security authority or its canonical
portfolio/instrument parents. Identical version-1 replay is idempotent. Changed source evidence
must use a governed newer source version; use an explicit full local-state reset for incompatible
experimental history rather than deleting append-only evidence from a portfolio cleanup.

`--skip-cleanup` preserves transaction history but is not a no-op. For an existing seed it
updates the portfolio master only when durable `LOTUS_PB_SG` / `SG_PRIVATE_BANK_BOOK` scope is
wrong, waits for existing instruments, and publishes only raw-price observations missing from the
complete required windows. Existing observations must match the canonical price and currency;
conflicts fail closed instead of being blessed by new source authority. The tool then publishes and
durably verifies valuation assignments/source facts before continuing. It never replays
transactions or rearms unchanged source parents unless the separate governed reprocess option is
selected.

The app-local Core stack runs four bounded portfolio aggregation workers by default. The scheduler
claims ready portfolio-day rows from `portfolio_aggregation_jobs` with `FOR UPDATE SKIP LOCKED` and
durable lease fencing, so the canonical one-portfolio, many-business-day seed can drain in parallel
without an internal Kafka command hop. Operators can tune bounded concurrency with
`PORTFOLIO_AGGREGATION_WORKER_COUNT` and claim recovery with
`AGGREGATION_JOB_LEASE_DURATION_SECONDS`.

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
