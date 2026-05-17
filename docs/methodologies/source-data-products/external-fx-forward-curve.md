# External FX Forward Curve Methodology

## Metric

`ExternalFXForwardCurve:v1` is the core-owned external treasury FX forward curve posture product
exposed by `POST /integration/market-data/external-fx-forward-curve`.

It returns a deterministic fail-closed unavailable posture until bank-owned treasury forward-curve
ingestion is certified. The product is supportability evidence only. It does not price forwards,
perform FX valuation, recommend hedges, select counterparties, generate treasury instructions,
route orders, certify best execution, acknowledge OMS activity, certify fills, confirm settlement,
or perform autonomous treasury action.

## Endpoint and Mode Coverage

| Request shape | Implemented behavior |
| --- | --- |
| `as_of_date` | Business date used for product runtime identity and fail-closed supportability. |
| optional `tenant_id` | Included in runtime metadata and deterministic fingerprints. |
| optional `reporting_currency` | Echoed for downstream audit only; no conversion or valuation is performed. |
| optional `currency_pairs` | Echoed for downstream audit only; no pair-level forward points are resolved. |
| optional `tenors` | Echoed for downstream audit only; no tenor interpolation or curve construction is performed. |

The current implemented mode is fail-closed source posture. There is no local forward-pricing mode,
no interpolation mode, no yield-curve/discounting mode, no counterparty quote mode, and no
bank-owned treasury ingestion mode.

## Inputs

| Input | Source | Required | Meaning |
| --- | --- | --- | --- |
| `as_of_date` | Request body | Yes | Business date used for source posture and runtime metadata. |
| `tenant_id` | Request body | No | Tenant scope included in runtime source-data metadata. |
| `reporting_currency` | Request body | No | Downstream reporting currency echoed for audit. |
| `currency_pairs` | Request body | No, default empty | Requested ISO currency pairs echoed for audit. |
| `tenors` | Request body | No, default empty | Requested forward tenors echoed for audit. |

## Upstream Data Sources

| Source | Used fields | Inclusion rule |
| --- | --- | --- |
| Bank-owned treasury FX forward curve source | none ingested | Not certified in the current runtime. The product always reports the family as missing. |

## Unit Conventions

The product returns no forward points, rates, pips, discount factors, spot rates, or monetary
amounts in the current runtime. It returns supportability state, missing data families, blocked
capabilities, audit echoes, lineage, and runtime source-data metadata.

Currency pairs and tenors are treated as opaque request identifiers for audit. Core does not parse
pair direction, infer reciprocal pairs, normalize tenor calendars, interpolate missing tenors, or
derive curve points.

## Variable Dictionary

| Symbol | Response or source field | Definition |
| --- | --- | --- |
| `A` | `as_of_date` | Business date for product runtime identity. |
| `R` | `reporting_currency` | Optional reporting currency echoed for audit. |
| `P_req` | `currency_pairs` | Optional requested currency pairs echoed for audit. |
| `T_req` | `tenors` | Optional requested tenors echoed for audit. |
| `CURVE` | `curve_points` | External treasury FX forward curve rows. Current runtime returns `[]`. |
| `n_CURVE` | `supportability.curve_point_count` | Count of returned curve points. Current runtime returns `0`. |
| `F_missing` | `supportability.missing_data_families` | Required source-data family not certified for use. |
| `B_blocked` | `supportability.blocked_capabilities` | Capabilities explicitly blocked while external curve data is unavailable. |

## Methodology and Formulas

The current posture is deterministic:

`CURVE = []`

`n_CURVE = len(CURVE) = 0`

`F_missing = ["external_fx_forward_curve"]`

`B_blocked = ["forward_pricing", "fx_valuation_methodology", "hedge_advice", "treasury_instruction", "counterparty_selection", "order_generation", "best_execution", "venue_routing", "oms_acknowledgement", "fills", "settlement", "autonomous_treasury_action"]`

`supportability.state = "UNAVAILABLE"`

`supportability.reason = "EXTERNAL_TREASURY_SOURCE_NOT_INGESTED"`

`data_quality_status = "MISSING"`

The source batch fingerprint is computed from product name, as-of date, requested reporting
currency, sorted requested currency pairs, sorted requested tenors, and the fixed integration
status `not_ingested`. The snapshot id uses the same deterministic posture with the
`external_fx_forward_curve:` prefix.

## Step-by-Step Computation

1. Preserve optional `reporting_currency`, `currency_pairs`, and `tenors` as audit echoes only.
2. Set `curve_points` to an empty list and `curve_point_count` to `0`.
3. Set missing data family to `external_fx_forward_curve`.
4. Set blocked capabilities to forward pricing, FX valuation methodology, hedge advice, treasury
   instruction, counterparty selection, order generation, best execution, venue routing, OMS
   acknowledgement, fills, settlement, and autonomous treasury action.
5. Emit lineage with source system `external-bank-treasury`, source table `not_ingested`, contract
   version `rfc_039_external_fx_forward_curve_v1`, runtime posture `fail_closed`, and
   blocked-capability non-claims.
6. Emit runtime source-data metadata with `data_quality_status=MISSING`, no latest evidence
   timestamp, and deterministic fingerprints.

## Validation and Failure Behavior

| Condition | Behavior |
| --- | --- |
| Treasury curve ingestion is not certified | Response returns supportability `UNAVAILABLE` and reason `EXTERNAL_TREASURY_SOURCE_NOT_INGESTED`. |
| `reporting_currency` is supplied | Value is echoed for audit only and does not trigger FX conversion or valuation. |
| `currency_pairs` are supplied | Values are echoed for audit only and do not trigger treasury lookup, reciprocal-pair inference, or forward pricing. |
| `tenors` are supplied | Values are echoed for audit only and do not trigger interpolation, curve construction, or missing-tenor substitution. |
| Duplicate or unknown currency pairs or tenors are supplied | Current fail-closed posture does not classify them; treasury ingestion must be certified before pair/tenor-level status can be claimed. |

`data_quality_status` is `MISSING` because no external treasury curve source table is certified.
Consumers must fail closed when this product is required for currency-overlay realization.

## Configuration Options

| Option | Current value |
| --- | --- |
| Product identity | `ExternalFXForwardCurve:v1` |
| Supportability state | `UNAVAILABLE` |
| Supportability reason | `EXTERNAL_TREASURY_SOURCE_NOT_INGESTED` |
| Missing data family | `external_fx_forward_curve` |
| Curve points | Always empty until bank-owned treasury curve ingestion is certified |
| Latest evidence timestamp | `null` |

## Outputs

| Field | Methodology mapping |
| --- | --- |
| `reporting_currency` | Request echo `R`; audit only. |
| `currency_pairs` | Request echo `P_req`; audit only. |
| `tenors` | Request echo `T_req`; audit only. |
| `curve_points` | `CURVE`, currently `[]`. |
| `supportability.curve_point_count` | `n_CURVE`, currently `0`. |
| `supportability.missing_data_families` | `F_missing`. |
| `supportability.blocked_capabilities` | `B_blocked`. |
| `lineage` | External treasury source system, not-ingested table posture, contract version, fail-closed runtime posture, and non-claims. |

## Worked Example

Request:

`POST /integration/market-data/external-fx-forward-curve`

```json
{
  "as_of_date": "2026-05-03",
  "reporting_currency": "USD",
  "currency_pairs": ["EUR/USD", "USD/JPY"],
  "tenors": ["1M", "3M", "6M"]
}
```

Resolved source facts:

| Source fact | Value |
| --- | --- |
| Treasury curve source table | `not_ingested` |
| Certified FX forward curve points | none |
| Requested pairs | `EUR/USD`, `USD/JPY` |
| Requested tenors | `1M`, `3M`, `6M` |

Final output mapping:

| Response field | Value |
| --- | --- |
| `supportability.state` | `UNAVAILABLE` |
| `supportability.reason` | `EXTERNAL_TREASURY_SOURCE_NOT_INGESTED` |
| `supportability.curve_point_count` | `0` |
| `curve_points` | `[]` |
| `supportability.missing_data_families[0]` | `external_fx_forward_curve` |
| `supportability.blocked_capabilities` | forward pricing, FX valuation methodology, hedge advice, treasury instruction, counterparty selection, order generation, best execution, venue routing, OMS acknowledgement, fills, settlement, autonomous treasury action |
| `data_quality_status` | `MISSING` |

## Downstream Consumption Rules

Consumers may use the unavailable posture to block forward-curve-dependent currency-overlay
realization and route operators to treasury source-integration work. Downstream services must not
invent forward points, infer hedge pricing, select counterparties, create treasury instructions,
route orders, claim best execution, or certify OMS/fill/settlement truth from this Core source
posture.
