# External Eligible Hedge Instrument Methodology

## Metric

`ExternalEligibleHedgeInstrument:v1` is the core-owned external treasury eligible hedge instrument
posture product exposed by
`POST /integration/portfolios/{portfolio_id}/external-eligible-hedge-instruments`.

It returns a deterministic fail-closed unavailable posture until bank-owned treasury instrument
eligibility ingestion is certified. The product is supportability evidence only. It does not select
eligible hedge instruments, determine hedge-instrument suitability, recommend products, select
counterparties, generate treasury instructions, create orders, certify best execution, acknowledge
OMS activity, certify fills, confirm settlement, or perform autonomous treasury action.

## Endpoint and Mode Coverage

| Request shape | Implemented behavior |
| --- | --- |
| `portfolio_id` | Resolves active discretionary mandate binding for the requested as-of date. |
| `as_of_date` | Business date used for mandate binding, product runtime identity, and fail-closed supportability. |
| optional `tenant_id` | Included in runtime metadata and deterministic fingerprints. |
| optional `mandate_id` | Optional mandate disambiguator passed to mandate binding resolution. |
| optional `reporting_currency` | Echoed for downstream audit only; no conversion or valuation is performed. |
| optional `exposure_currencies` | Echoed for downstream audit only; no exposure-level eligibility is resolved. |
| optional `instrument_types` | Echoed for downstream audit only; no product shelf or suitability decision is made. |

The current implemented mode is fail-closed source posture. There is no local product-shelf
eligibility mode, no suitability mode, no product recommendation mode, no counterparty-selection
mode, no order-generation mode, and no bank-owned treasury ingestion mode.

## Inputs

| Input | Source | Required | Meaning |
| --- | --- | --- |
| `portfolio_id` | Path | Yes | Portfolio whose mandate identity is resolved. |
| `as_of_date` | Request body | Yes | Business date used for mandate binding and runtime metadata. |
| `tenant_id` | Request body | No | Tenant scope included in runtime source-data metadata. |
| `mandate_id` | Request body | No | Optional mandate disambiguator. |
| `reporting_currency` | Request body | No | Downstream reporting currency echoed for audit. |
| `exposure_currencies` | Request body | No, default empty | Requested exposure currencies echoed for audit. |
| `instrument_types` | Request body | No, default empty | Requested external treasury instrument types echoed for audit. |

## Upstream Data Sources

| Source | Used fields | Inclusion rule |
| --- | --- | --- |
| `DiscretionaryMandateBinding:v1` | `client_id`, `mandate_id` | Required to identify the active discretionary mandate for the portfolio and as-of date. |
| Bank-owned treasury eligible-instrument source | none ingested | Not certified in the current runtime. The product always reports the eligible-instrument family as missing. |

## Unit Conventions

The product returns no eligible instrument rows, suitability scores, product terms, counterparty
lists, order identifiers, best-execution evidence, fill quantities, or settlement facts in the
current runtime. It returns supportability state, missing data family, blocked capabilities, audit
echoes, mandate identity, lineage, and runtime source-data metadata.

Exposure currencies and instrument types are treated as opaque request identifiers for audit. Core
does not normalize currency exposure, infer product eligibility, map product shelves, rank
instruments, or substitute treasury evidence.

## Variable Dictionary

| Symbol | Response or source field | Definition |
| --- | --- | --- |
| `P` | `portfolio_id` | Portfolio identifier from the path. |
| `C` | `client_id` | Client identifier from active mandate binding. |
| `M` | `mandate_id` | Mandate identifier from active mandate binding. |
| `A` | `as_of_date` | Business date for mandate binding and product runtime identity. |
| `R` | `reporting_currency` | Optional reporting currency echoed for audit. |
| `E_req` | `exposure_currencies` | Optional requested exposure currencies echoed for audit. |
| `T_req` | `instrument_types` | Optional requested instrument types echoed for audit. |
| `INSTR` | `eligible_instruments` | External treasury eligible hedge instrument rows. Current runtime returns `[]`. |
| `n_INSTR` | `supportability.instrument_count` | Count of returned eligible hedge instrument rows. Current runtime returns `0`. |
| `F_missing` | `supportability.missing_data_families` | Required source-data family not certified for use. |
| `B_blocked` | `supportability.blocked_capabilities` | Capabilities explicitly blocked while eligible-instrument data is unavailable. |

## Methodology and Formulas

The current posture is deterministic after mandate binding resolves:

`INSTR = []`

`n_INSTR = len(INSTR) = 0`

`F_missing = ["external_eligible_hedge_instrument"]`

`B_blocked = ["eligible_hedge_instrument_selection", "hedge_instrument_suitability", "product_recommendation", "counterparty_selection", "treasury_instruction", "order_generation", "best_execution", "oms_acknowledgement", "fills", "settlement", "autonomous_treasury_action"]`

`supportability.state = "UNAVAILABLE"`

`supportability.reason = "EXTERNAL_TREASURY_SOURCE_NOT_INGESTED"`

`data_quality_status = "MISSING"`

The source batch fingerprint is computed from product name, portfolio id, resolved client id,
resolved mandate id, as-of date, requested reporting currency, sorted requested exposure
currencies, sorted requested instrument types, and the fixed integration status `not_ingested`.
The snapshot id uses the `external_eligible_hedge_instrument:` prefix.

## Step-by-Step Computation

1. Resolve active discretionary mandate binding for `portfolio_id`, `as_of_date`, and optional
   `mandate_id`.
2. If mandate binding is absent, return no product response so the API layer can fail closed with
   not-found semantics.
3. Preserve optional `reporting_currency`, `exposure_currencies`, and `instrument_types` as audit
   echoes only.
4. Set `eligible_instruments` to an empty list and `instrument_count` to `0`.
5. Set missing data family to `external_eligible_hedge_instrument`.
6. Set blocked capabilities to eligible hedge instrument selection, hedge instrument suitability,
   product recommendation, counterparty selection, treasury instruction, order generation, best
   execution, OMS acknowledgement, fills, settlement, and autonomous treasury action.
7. Emit lineage with source system `external-bank-treasury`, source table `not_ingested`, contract
   version `rfc_039_external_eligible_hedge_instrument_v1`, runtime posture `fail_closed`, and
   blocked-capability non-claims.
8. Emit runtime source-data metadata with `data_quality_status=MISSING`, no latest evidence
   timestamp, and deterministic fingerprints.

## Validation and Failure Behavior

| Condition | Behavior |
| --- | --- |
| Active mandate binding is absent | The service returns no product response; the API layer returns not found for the requested portfolio/date/mandate context. |
| Treasury instrument eligibility ingestion is not certified | Response returns supportability `UNAVAILABLE` and reason `EXTERNAL_TREASURY_SOURCE_NOT_INGESTED`. |
| `reporting_currency` is supplied | Value is echoed for audit only and does not trigger FX conversion or valuation. |
| `exposure_currencies` are supplied | Values are echoed for audit only and do not trigger eligibility lookup or hedge advice. |
| `instrument_types` are supplied | Values are echoed for audit only and do not trigger product shelf filtering, suitability, or recommendation. |
| Duplicate or unknown exposure currencies or instrument types are supplied | Current fail-closed posture does not classify them; treasury ingestion must be certified before row-level eligibility can be claimed. |

`data_quality_status` is `MISSING` because no external treasury eligible-instrument source table is
certified. Consumers must fail closed when this product is required for currency-overlay
realization.

## Configuration Options

| Option | Current value |
| --- | --- |
| Product identity | `ExternalEligibleHedgeInstrument:v1` |
| Supportability state | `UNAVAILABLE` |
| Supportability reason | `EXTERNAL_TREASURY_SOURCE_NOT_INGESTED` |
| Missing data family | `external_eligible_hedge_instrument` |
| Eligible instruments | Always empty until bank-owned treasury instrument eligibility ingestion is certified |
| Latest evidence timestamp | `null` |

## Outputs

| Field | Methodology mapping |
| --- | --- |
| `portfolio_id` | Request path `P`. |
| `client_id` | Active mandate binding `C`. |
| `mandate_id` | Active mandate binding `M`. |
| `reporting_currency` | Request echo `R`; audit only. |
| `exposure_currencies` | Request echo `E_req`; audit only. |
| `instrument_types` | Request echo `T_req`; audit only. |
| `eligible_instruments` | `INSTR`, currently `[]`. |
| `supportability.instrument_count` | `n_INSTR`, currently `0`. |
| `supportability.missing_data_families` | `F_missing`. |
| `supportability.blocked_capabilities` | `B_blocked`. |
| `lineage` | External treasury source system, not-ingested table posture, contract version, fail-closed runtime posture, and non-claims. |

## Worked Example

Request:

`POST /integration/portfolios/PB_SG_GLOBAL_BAL_001/external-eligible-hedge-instruments`

```json
{
  "as_of_date": "2026-05-03",
  "reporting_currency": "USD",
  "exposure_currencies": ["EUR", "JPY"],
  "instrument_types": ["FX_FORWARD", "FX_SWAP"]
}
```

Resolved source facts:

| Source fact | Value |
| --- | --- |
| Active mandate binding | resolved for `PB_SG_GLOBAL_BAL_001` |
| Treasury eligible-instrument source table | `not_ingested` |
| Certified eligible hedge instruments | none |
| Requested exposure currencies | `EUR`, `JPY` |
| Requested instrument types | `FX_FORWARD`, `FX_SWAP` |

Final output mapping:

| Response field | Value |
| --- | --- |
| `supportability.state` | `UNAVAILABLE` |
| `supportability.reason` | `EXTERNAL_TREASURY_SOURCE_NOT_INGESTED` |
| `supportability.instrument_count` | `0` |
| `eligible_instruments` | `[]` |
| `supportability.missing_data_families[0]` | `external_eligible_hedge_instrument` |
| `supportability.blocked_capabilities` | eligible hedge instrument selection, hedge instrument suitability, product recommendation, counterparty selection, treasury instruction, order generation, best execution, OMS acknowledgement, fills, settlement, autonomous treasury action |
| `data_quality_status` | `MISSING` |

## Downstream Consumption Rules

Consumers may use the unavailable posture to block eligible-instrument-dependent currency-overlay
realization and route operators to treasury source-integration work. Downstream services must not
invent product eligibility, infer suitability, recommend an instrument, choose counterparties,
generate treasury instructions or orders, claim best execution, acknowledge OMS activity, certify
fills, confirm settlement, or perform autonomous treasury action from this Core source posture.
