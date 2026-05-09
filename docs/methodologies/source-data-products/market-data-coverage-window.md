# Market Data Coverage Window Methodology

## Metric

`MarketDataCoverageWindow:v1` is the core-owned DPM market-price and FX coverage diagnostic
product exposed by `POST /integration/market-data/coverage`.

It returns latest available price observations for requested held and target instruments, latest
available FX observations for requested currency pairs, per-observation freshness status, batch
supportability, runtime source-data-product metadata, and lineage. The product is source evidence
for market-data availability and freshness. It is not a valuation methodology, FX attribution
methodology, liquidity ladder, cash forecast, market-impact model, execution-quality assessment, or
OMS acknowledgement.

## Endpoint and Mode Coverage

| Mode | Request shape | Implemented behavior |
| --- | --- | --- |
| Price coverage | `instrument_ids=[...]` | Resolves the latest market price on or before `as_of_date` for each requested instrument. |
| FX coverage | `currency_pairs=[{from_currency,to_currency}, ...]` | Resolves the latest FX rate on or before `as_of_date` for each requested pair. |
| Combined DPM universe coverage | Both price and FX inputs supplied | Returns price and FX records in one supportability envelope so manage can evaluate held and target universe readiness without serial lookups. |
| Staleness override | `max_staleness_days=<n>` | Marks found observations older than the threshold as `STALE`; default threshold is five calendar days. |
| Valuation-currency context | `valuation_currency=<ccy>` | Carries requested target valuation currency for lineage and downstream diagnostics. It does not infer missing currency pairs or perform valuation. |

## Inputs

| Input | Source | Required | Meaning |
| --- | --- | --- | --- |
| `as_of_date` | Request body | Yes | Date used as the upper bound for latest price and FX observation lookup. |
| `instrument_ids` | Request body | No | Held and target instrument identifiers requiring price coverage. |
| `currency_pairs` | Request body | No | Explicit FX conversion pairs requiring rate coverage. |
| `valuation_currency` | Request body | No | Optional valuation-currency context carried into response lineage. |
| `max_staleness_days` | Request body | No, default `5` | Maximum accepted calendar age before a found observation is marked stale. |
| `tenant_id` | Request body | No | Optional lineage and future policy context. |

## Upstream Data Sources

| Source | Used fields | Inclusion rule |
| --- | --- | --- |
| `market_prices` | `security_id`, `price_date`, `price`, `currency`, `updated_at` | Latest row where `security_id` matches the requested instrument and `price_date <= as_of_date`. |
| `fx_rates` | `from_currency`, `to_currency`, `rate_date`, `rate`, `updated_at` | Latest row where the currency pair matches the request and `rate_date <= as_of_date`. |

## Unit Conventions

Price values preserve the source price currency. FX rates preserve the stored pair direction:
`from_currency -> to_currency`. Age is measured in calendar days:

`age_days = as_of_date - observation_date`

The response does not convert prices, calculate position values, derive FX P&L, aggregate cash
movements, or choose execution assumptions.

## Variable Dictionary

| Symbol | Response or source field | Definition |
| --- | --- | --- |
| `A` | `as_of_date` | Requested coverage date. |
| `S` | `instrument_ids` | Requested price-coverage security set. |
| `C` | `currency_pairs` | Requested FX-coverage pair set. |
| `M_s` | `market_prices` row | Latest price row for security `s` on or before `A`. |
| `F_c` | `fx_rates` row | Latest FX row for pair `c` on or before `A`. |
| `D` | `max_staleness_days` | Calendar-day freshness threshold. |
| `age(x)` | `age_days` | Calendar days between `A` and the resolved observation date. |
| `Q_i` | `quality_status` | Per-price or per-FX status: `READY`, `STALE`, or `MISSING`. |
| `B` | `supportability.state` | Batch state: `READY`, `DEGRADED`, `INCOMPLETE`, or `UNAVAILABLE`. |

## Methodology and Formulas

For each requested instrument `s`, the resolved price row is:

`M_s = latest market_prices where security_id = s and price_date <= A`

If no row exists, the price record is `MISSING`.

If a row exists:

`age(M_s) = A - M_s.price_date`

`Q_s = STALE if age(M_s) > D else READY`

For each requested currency pair `c = from/to`, the resolved FX row is:

`F_c = latest fx_rates where from_currency = from and to_currency = to and rate_date <= A`

If no row exists, the FX record is `MISSING`.

If a row exists:

`age(F_c) = A - F_c.rate_date`

`Q_c = STALE if age(F_c) > D else READY`

Batch supportability is derived in priority order:

1. `INCOMPLETE` / `MARKET_DATA_MISSING` when any requested price or FX row is missing,
2. `DEGRADED` / `MARKET_DATA_STALE` when no rows are missing but at least one found row is stale,
3. `READY` / `MARKET_DATA_READY` when all requested rows are found and fresh.

`data_quality_status` is `COMPLETE` only when batch supportability is `READY`; otherwise it is
`PARTIAL`.

## Step-by-Step Computation

1. Normalize request currency codes and reject duplicate instruments or duplicate currency pairs.
2. Query latest market prices for all requested instruments with `price_date <= as_of_date`.
3. Query latest FX rates for all requested currency pairs with `rate_date <= as_of_date`.
4. Emit one price coverage row per requested instrument, preserving request order.
5. Emit one FX coverage row per requested currency pair, preserving request order.
6. Classify each found row as `READY` or `STALE` from calendar-day age and `max_staleness_days`.
7. Classify missing rows as `MISSING`.
8. Build batch supportability from missing and stale sets.
9. Populate runtime metadata from the latest available price or FX `updated_at` timestamp.

## Validation and Failure Behavior

| Condition | Output behavior |
| --- | --- |
| Duplicate `instrument_ids` | Request validation fails. |
| Duplicate `currency_pairs` | Request validation fails. |
| Instrument price not found | Price row has `found=false`, `quality_status=MISSING`, and the instrument id appears in `missing_instrument_ids`. |
| FX rate not found | FX row has `found=false`, `quality_status=MISSING`, and the pair label appears in `missing_currency_pairs`. |
| Found price older than `max_staleness_days` | Price row has `quality_status=STALE`, and the instrument id appears in `stale_instrument_ids`. |
| Found FX rate older than `max_staleness_days` | FX row has `quality_status=STALE`, and the pair label appears in `stale_currency_pairs`. |
| All requested observations found and fresh | `supportability.state=READY`, reason `MARKET_DATA_READY`, data quality `COMPLETE`. |
| Missing observations exist | `supportability.state=INCOMPLETE`, reason `MARKET_DATA_MISSING`, data quality `PARTIAL`. |
| No missing observations but stale observations exist | `supportability.state=DEGRADED`, reason `MARKET_DATA_STALE`, data quality `PARTIAL`. |

## Output Contract

The response preserves:

1. requested as-of date and valuation-currency context,
2. one price coverage row per requested instrument,
3. one FX coverage row per requested currency pair,
4. requested and resolved price/FX counts,
5. missing and stale identifiers,
6. supportability state and bounded reason code,
7. source-data-product runtime metadata,
8. lineage with `source_system=market_prices+fx_rates` and `contract_version=rfc_087_v1`.

## Worked Example

Request:

```json
{
  "as_of_date": "2026-04-10",
  "instrument_ids": ["EQ_US_AAPL", "FI_US_TREASURY_10Y", "UNKNOWN_SEC"],
  "currency_pairs": [{"from_currency": "USD", "to_currency": "SGD"}],
  "valuation_currency": "SGD",
  "max_staleness_days": 5
}
```

Source observations:

| Source | Key | Observation date | Value | Currency/pair |
| --- | --- | --- | --- | --- |
| `market_prices` | `EQ_US_AAPL` | `2026-04-10` | `187.1200000000` | `USD` |
| `market_prices` | `FI_US_TREASURY_10Y` | `2026-04-01` | `98.5000000000` | `USD` |
| `fx_rates` | `USD/SGD` | `2026-04-10` | `1.3521000000` | `USD -> SGD` |

Result:

| Record | Status | Reason |
| --- | --- | --- |
| `EQ_US_AAPL` price | `READY` | Price exists on `as_of_date`. |
| `FI_US_TREASURY_10Y` price | `STALE` | Age is nine calendar days, greater than threshold five. |
| `UNKNOWN_SEC` price | `MISSING` | No price exists on or before `as_of_date`. |
| `USD/SGD` FX | `READY` | FX rate exists on `as_of_date`. |

Batch supportability is `INCOMPLETE` with reason `MARKET_DATA_MISSING` because missing evidence
takes precedence over stale evidence.

## Downstream Consumption Rules

Downstream consumers may:

1. use coverage rows to decide whether a DPM workflow can value a requested instrument universe,
2. surface missing and stale market-data diagnostics to operations,
3. preserve price/FX evidence timestamps, counts, and identifiers in proof packs or readiness
   summaries,
4. route incomplete or degraded source readiness without local inference.

Downstream consumers must not:

1. infer FX attribution or realized FX P&L from coverage rows,
2. calculate portfolio valuation, liquidity ladders, or cash forecasts from coverage diagnostics
   alone,
3. treat stale-but-found data as approved for trading without an owning policy,
4. infer market impact, best execution, venue routing, or OMS acknowledgement,
5. reconstruct missing source facts outside the source owner.
