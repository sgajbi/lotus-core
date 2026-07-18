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
| `include_projected` | Query parameter | No, fixed `false` | Projected holdings are excluded from this trust-certified receipt. Supplying `true` returns HTTP 422. |
| `X-Tenant-Id` | Request header | No | Tenant identity bound into the receipt and deterministic input lineage when supplied. |

## Source Data

The summary consumes the same Core application path as `GET /portfolios/{portfolio_id}/positions`.
It inherits HoldingsAsOf effective-date resolution, current-epoch position selection, snapshot and
history supplement behavior, market-price freshness posture, latest evidence timestamp, and
runtime source-data metadata.

For each selected snapshot or history row, Core preserves the exact source business date and
current epoch before DTO mapping. One set-based indexed read resolves the durable
`FINANCIAL_RECONCILIATION` aggregate control row for every unique portfolio-day/epoch scope. Core
does not perform one reconciliation query per holding. A missing scope, an epoch mismatch, or an
empty book without control evidence remains unreconciled; it is never promoted to complete from
holdings quality alone.

## Methodology

1. Require `include_projected=false`, then resolve booked `HoldingsAsOf:v1` for the portfolio and
   optional `as_of_date`.
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
9. Classify each exact HoldingsAsOf source scope from its durable aggregate control:
   - `COMPLETED` at or after the latest selected source evidence -> `COMPLETE`,
   - `PENDING`, `RUNNING`, `PROCESSING`, or `QUEUED` -> `PARTIAL`,
   - `FAILED`, `REQUIRES_REPLAY`, or `BLOCKED` -> `BLOCKED`,
   - a completed control older than selected source evidence -> `STALE`,
   - missing control -> `UNRECONCILED`, and an unrecognized or unscoped row -> `UNKNOWN`.
   The response uses the most severe posture across all exact source scopes.
10. Set `freshness_status=CURRENT` only when holdings quality is `COMPLETE` or `PARTIAL` and
    reconciliation is `COMPLETE`; preserve `STALE` when either source or control evidence is stale.
11. Derive supportability reason codes from HoldingsAsOf quality, reconciliation posture, missing
    maturity facts, and unsupported product-feature indicators. Reconciliation other than
    `COMPLETE` can never produce `supportability_status=SUPPORTED`.
12. Build three deterministic SHA-256 lineage layers with algorithm id
    `PORTFOLIO_CONTRACTUAL_MATURITY_SUMMARY`, version `1`:
    - input: portfolio, normalized tenant, booked projection flag, horizon, exact HoldingsAsOf
      product/as-of/snapshot/content/source-batch/policy/latest-evidence/reconciliation identity;
    - calculation: algorithm id, version, integer/date intermediate precision, and input hash;
    - output: window, counts, next maturity, and supportability output bound to the calculation hash.
13. Derive `request_fingerprint` from the normalized input hash and publish the response content
    hash as the source digest and source-batch fingerprint. Request correlation is propagated as
    operational evidence but intentionally excluded from deterministic financial hashes.

## Supportability

| Condition | Output posture |
| --- | --- |
| HoldingsAsOf quality is `UNKNOWN` | `supportability_status=UNAVAILABLE`, `supportability_reasons=["HOLDINGS_UNKNOWN"]`. |
| HoldingsAsOf quality is `STALE` | `supportability_status=STALE`, `supportability_reasons` includes `HOLDINGS_STALE`. |
| HoldingsAsOf quality is `PARTIAL` | `supportability_status=PARTIAL`, `supportability_reasons` includes `HOLDINGS_PARTIAL`. |
| Exact reconciliation is missing | `reconciliation_status=UNRECONCILED`, `supportability_status=UNAVAILABLE`, reason `HOLDINGS_RECONCILIATION_MISSING`. |
| Exact reconciliation is incomplete | `reconciliation_status=PARTIAL`, `supportability_status=PARTIAL`, reason `HOLDINGS_RECONCILIATION_PARTIAL`. |
| Exact reconciliation is stale | `reconciliation_status=STALE`, `supportability_status=STALE`, reason `HOLDINGS_RECONCILIATION_STALE`. |
| Exact reconciliation failed or requires replay | `reconciliation_status=BLOCKED`, `supportability_status=UNAVAILABLE`, reason `HOLDINGS_RECONCILIATION_BLOCKED`. |
| Exact reconciliation is unknown or a source row cannot be scoped | `reconciliation_status=UNKNOWN`, `supportability_status=UNAVAILABLE`, reason `HOLDINGS_RECONCILIATION_UNKNOWN`. |
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
| `tenant_id`, `correlation_id` | Caller tenant when supplied and request correlation propagated by Core middleware. |
| `snapshot_id`, `content_hash`, `source_digest`, `source_batch_fingerprint`, `policy_version` | Exact HoldingsAsOf source identity and deterministic maturity receipt identity. |
| `reconciliation_status` | Aggregate exact-scope portfolio-day/epoch control posture. |
| `freshness_status` | Combined HoldingsAsOf evidence and reconciliation freshness posture. |
| `supportability_status`, `supportability_reasons` | Bounded posture and reason codes for downstream fail-closed handling. |
| `request_fingerprint` | Deterministic product/request fingerprint for replay and lineage. |
| `calculation_lineage` | Separate normalized-input, calculation-policy, and output SHA-256 hashes. |

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
| `reconciliation_status` | `COMPLETE` |
| `supportability_status` | `SUPPORTED` |
| `calculation_lineage.algorithm_id` | `PORTFOLIO_CONTRACTUAL_MATURITY_SUMMARY` |

The worked example is supported only when every selected source business-date/epoch scope has a
current `COMPLETED` financial-reconciliation control. The same holdings rows with missing control
evidence return the same bounded maturity counts but an unavailable trust posture.
