# Portfolio Maturity Summary Methodology

## Metric

`PortfolioMaturitySummary:v1` is the Core-owned operational read exposed by:

1. `GET /portfolios/{portfolio_id}/maturity-summary`.

It summarizes contractual instrument maturity-date facts from the resolved `HoldingsAsOf:v1`
position scope for one portfolio and bounded calendar-day horizon. The product gives downstream
consumers, including `lotus-idea`, source-owned maturity posture without requiring them to scan raw
holdings rows or implement instrument lifecycle interpretation locally.

This product is source evidence for contractual maturity posture. It is not a full maturity
schedule, cashflow forecast, liquidity ladder, reinvestment recommendation, risk methodology,
performance methodology, tax advice, execution-quality assessment, or OMS acknowledgement.

## Inputs

| Input | Source | Required | Meaning |
| --- | --- | --- | --- |
| `portfolio_id` | Path parameter | Yes | Portfolio whose maturity posture is queried. |
| `as_of_date` | Query parameter | No | Booked HoldingsAsOf cap used as the summary start date. |
| `horizon_days` | Query parameter | No, default `90`, max `3660` | Calendar-day horizon used to derive the inclusive maturity window end date. |
| `include_projected` | Query parameter | No, default `false` | Controls whether projected holdings are included in the underlying HoldingsAsOf read. |

## Source Data

The summary consumes the same Core application path as `GET /portfolios/{portfolio_id}/positions`.
It inherits HoldingsAsOf effective-date resolution, current-epoch position selection, snapshot and
history supplement behavior, market-price freshness posture, latest evidence timestamp, and
runtime source-data metadata.

## Methodology

1. Resolve `HoldingsAsOf:v1` for the portfolio, optional `as_of_date`, and `include_projected`.
2. Set `window_start_date = HoldingsAsOf.as_of_date`.
3. Set `window_end_date = window_start_date + horizon_days`.
4. Classify returned holdings as maturity-bearing when `asset_class` or `product_type` contains
   fixed-income/debt terms such as bond, note, bill, debenture, or fixed income.
5. Count maturity-bearing holdings where `maturity_date` is missing as
   `missing_maturity_date_count`.
6. Count returned holdings whose classification suggests callable, putable, amortizing, structured,
   lockup, expiry, or expiration features as `unsupported_maturity_feature_count`.
7. Count returned non-zero holdings whose source-owned `maturity_date` falls within the inclusive
   window as `maturing_holding_count`.
8. Set `next_maturity_date` to the earliest in-window maturity date, or null when none exists.
9. Inherit freshness from HoldingsAsOf data quality:
   - `COMPLETE` and `PARTIAL` -> `freshness_status=CURRENT`,
   - `STALE` -> `freshness_status=STALE`,
   - `UNKNOWN` -> `freshness_status=UNKNOWN`.
10. Derive supportability reason codes from HoldingsAsOf quality, missing maturity facts, and
    unsupported product-feature indicators.
11. Generate `request_fingerprint` from the requested scope and returned summary content. It is
    product/request lineage, not an upstream `source_batch_fingerprint`.

## Supportability

| Condition | Output posture |
| --- | --- |
| HoldingsAsOf quality is `UNKNOWN` | `supportability_status=UNAVAILABLE`, `supportability_reasons=["HOLDINGS_UNKNOWN"]`. |
| HoldingsAsOf quality is `STALE` | `supportability_status=STALE`, `supportability_reasons` includes `HOLDINGS_STALE`. |
| HoldingsAsOf quality is `PARTIAL` | `supportability_status=PARTIAL`, `supportability_reasons` includes `HOLDINGS_PARTIAL`. |
| Maturity-bearing holding lacks `maturity_date` | `supportability_status=PARTIAL`, `supportability_reasons` includes `MISSING_INSTRUMENT_MATURITY_DATE`. |
| Product classification suggests unsupported lifecycle features | `supportability_status=PARTIAL`, `supportability_reasons` includes `UNSUPPORTED_PRODUCT_MATURITY_FEATURE`. |
| No in-window maturity exists and no supportability reason applies | `next_maturity_date=null`, `maturing_holding_count=0`, `supportability_status=SUPPORTED`. |

The current implementation does not invent callable, putable, amortizing, structured-note, lockup,
or expiry schedules when Core reference data does not carry those lifecycle terms. Those cases must
remain visible as partial supportability rather than being reconstructed in downstream services.

## Outputs

| Field | Methodology mapping |
| --- | --- |
| `product_name`, `product_version` | `PortfolioMaturitySummary:v1`. |
| `source_product_name`, `source_product_version` | `HoldingsAsOf:v1`. |
| `as_of_date` | Resolved HoldingsAsOf response date. |
| `window_start_date`, `window_end_date` | Inclusive maturity summary window. |
| `next_maturity_date` | Earliest in-window source-owned instrument maturity date, or null. |
| `maturing_holding_count` | Count of returned non-zero holdings maturing in the window. |
| `maturity_bearing_holding_count` | Count of holdings classified as maturity-bearing. |
| `missing_maturity_date_count` | Count of maturity-bearing holdings missing a maturity date. |
| `unsupported_maturity_feature_count` | Count of holdings with classification terms outside the current contractual-date certification. |
| `freshness_status` | Freshness posture inherited from HoldingsAsOf quality. |
| `supportability_status`, `supportability_reasons` | Bounded posture and reason codes for downstream fail-closed handling. |
| `request_fingerprint` | Deterministic product/request fingerprint for replay and lineage. |

## Worked Example

Request:

`GET /portfolios/P1/maturity-summary?as_of_date=2026-03-10&horizon_days=90`

Source positions:

| Security | Asset class | Product type | Quantity | Maturity date |
| --- | --- | --- | ---: | --- |
| `BOND-20260415` | Bond | Bond | 100 | 2026-04-15 |
| `BOND-20270115` | Bond | Bond | 50 | 2027-01-15 |
| `AAPL.OQ` | Equity | Equity | 25 | null |

Output posture:

| Field | Value |
| --- | --- |
| `window_start_date` | `2026-03-10` |
| `window_end_date` | `2026-06-08` |
| `next_maturity_date` | `2026-04-15` |
| `maturing_holding_count` | `1` |
| `maturity_bearing_holding_count` | `2` |
| `supportability_status` | `SUPPORTED` |
