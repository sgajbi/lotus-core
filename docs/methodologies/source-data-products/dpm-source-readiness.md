# DPM Source Readiness Methodology

## Purpose

`DpmSourceReadiness:v1` is the core-owned control-plane source product that summarizes whether a
portfolio has enough source-family evidence to promote stateful discretionary portfolio management
assembly. It is exposed through:

`POST /integration/portfolios/{portfolio_id}/dpm-source-readiness`

The product composes existing source products into one readiness envelope for operators and
downstream DPM services. It is not a mandate approval, model suitability decision, tax advice,
portfolio valuation, FX attribution methodology, liquidity ladder, execution-quality assessment,
best-execution certification, venue-routing model, or OMS acknowledgement.

## Supported Modes

| Mode | Request shape | Behavior |
| --- | --- | --- |
| Mandate-driven readiness | `portfolio_id`, `as_of_date`, optional `tenant_id`, optional `mandate_id` | Resolves the discretionary mandate binding and carries the resolved mandate/model identifiers into readiness lineage. |
| Model-target readiness | `model_portfolio_id` supplied or resolved from the mandate | Resolves approved model target instruments and contributes them to the evaluated DPM universe. |
| Caller-augmented readiness | `instrument_ids` supplied | Unions caller-known held instruments with resolved model target instruments before eligibility, tax-lot, and market-data checks. |
| FX-aware readiness | `currency_pairs`, optional `valuation_currency`, `max_staleness_days` supplied | Delegates market-price and FX freshness to `MarketDataCoverageWindow:v1`. |

## Inputs And Variables

| Variable | Source | Required | Meaning |
| --- | --- | --- | --- |
| `P` | Path parameter `portfolio_id` | Yes | Portfolio whose DPM source-family readiness is evaluated. |
| `A` | Request `as_of_date` | Yes | Effective source date used for every family. |
| `T` | Request `tenant_id` | No | Tenant lineage and future policy context. |
| `M_req` | Request `mandate_id` | No | Optional mandate disambiguator. |
| `MP_req` | Request `model_portfolio_id` | No | Optional model portfolio override. |
| `I_req` | Request `instrument_ids` | No | Caller-known held or target instruments. |
| `C` | Request `currency_pairs` | No | FX pairs required by downstream stateful DPM assembly. |
| `V` | Request `valuation_currency` | No | Target valuation-currency context for market-data readiness. |
| `S` | Request `max_staleness_days` | No | Maximum acceptable market-data age before stale classification. Defaults to `5`. |

## Source Tables And Products

`DpmSourceReadiness:v1` does not read private tables directly. It delegates to source products and
preserves their supportability:

| Family | Source product | Readiness contribution |
| --- | --- | --- |
| `mandate` | `DiscretionaryMandateBinding:v1` | Mandate/model/policy binding and mandate supportability. |
| `model_targets` | `DpmModelPortfolioTarget:v1` | Approved active target instruments for the resolved model portfolio. |
| `eligibility` | `InstrumentEligibilityProfile:v1` | Instrument shelf, restriction, settlement, and eligibility posture for the evaluated universe. |
| `tax_lots` | `PortfolioTaxLotWindow:v1` | Tax-lot and cost-basis source posture for the evaluated universe. |
| `market_data` | `MarketDataCoverageWindow:v1` | Price and FX coverage/freshness posture for the evaluated universe and requested currency pairs. |

## Methodology And Formulas

Resolve mandate binding:

`B = DiscretionaryMandateBinding(P, A, T, M_req)`

Resolve model portfolio:

`MP = MP_req if present else B.model_portfolio_id`

Resolve active model target instruments when `MP` is available:

`I_model = {target.instrument_id for target in DpmModelPortfolioTarget(MP, A, T)}`

Build the evaluated instrument universe:

`I_eval = sort(unique(I_req union I_model))`

Evaluate the remaining families:

`E = InstrumentEligibilityProfile(I_eval, A, T)`

`L = PortfolioTaxLotWindow(P, I_eval, A, T)`

`D = MarketDataCoverageWindow(I_eval, C, A, V, S, T)`

Each family emits a row:

`family_row = (family, product_name, state, reason, missing_items, stale_items, evidence_count)`

The overall supportability counts family states:

`ready_family_count = count(family.state == READY)`

`degraded_family_count = count(family.state == DEGRADED)`

`incomplete_family_count = count(family.state == INCOMPLETE)`

`unavailable_family_count = count(family.state == UNAVAILABLE)`

Overall state precedence is fail-closed:

1. if any family is `UNAVAILABLE`, overall state is `UNAVAILABLE` and reason is
   `DPM_SOURCE_READINESS_UNAVAILABLE`,
2. else if any family is `INCOMPLETE`, overall state is `INCOMPLETE` and reason is
   `DPM_SOURCE_READINESS_INCOMPLETE`,
3. else if any family is `DEGRADED`, overall state is `DEGRADED` and reason is
   `DPM_SOURCE_READINESS_DEGRADED`,
4. otherwise overall state is `READY` and reason is `DPM_SOURCE_READINESS_READY`.

## Deterministic Steps

1. Validate request DTO constraints, including non-empty and duplicate-free `instrument_ids`.
2. Attempt mandate binding resolution for `P`, `A`, `T`, and optional `M_req`.
3. If mandate binding fails or returns no response, append an `UNAVAILABLE`
   `MANDATE_BINDING_UNAVAILABLE` family row.
4. Resolve `MP` from request or mandate binding.
5. If `MP` is unavailable, append an `UNAVAILABLE` `MODEL_PORTFOLIO_ID_UNAVAILABLE` family row.
6. If `MP` is available, resolve active model targets; append the source product state and target
   count, or append `MODEL_TARGETS_UNAVAILABLE` on lookup/validation failure.
7. Build `I_eval` from request instruments and resolved target instruments.
8. If `I_eval` is empty, append an `UNAVAILABLE` `DPM_INSTRUMENT_UNIVERSE_EMPTY` eligibility row.
9. If `I_eval` is not empty, resolve instrument eligibility; append source supportability and
   resolved count, or append `INSTRUMENT_ELIGIBILITY_UNAVAILABLE` on lookup/validation failure.
10. Resolve portfolio tax lots for `P`, `A`, `T`, and `I_eval` when present; append source
    supportability and returned lot count, or append `PORTFOLIO_TAX_LOTS_UNAVAILABLE` on
    lookup/validation failure.
11. Resolve market-data coverage for `I_eval`, `C`, `A`, `V`, `S`, and `T`; append source
    supportability, missing items, stale items, and resolved observation count, or append
    `MARKET_DATA_COVERAGE_UNAVAILABLE` on lookup/validation failure.
12. Apply the fail-closed state precedence and return runtime source-data metadata.

## Validation And Failure Behavior

| Condition | Family state | Family reason | Overall effect |
| --- | --- | --- | --- |
| Mandate binding missing or invalid | `UNAVAILABLE` | `MANDATE_BINDING_UNAVAILABLE` | Overall `UNAVAILABLE`. |
| Model portfolio cannot be resolved | `UNAVAILABLE` | `MODEL_PORTFOLIO_ID_UNAVAILABLE` | Overall `UNAVAILABLE`. |
| Model targets missing or invalid | `UNAVAILABLE` | `MODEL_TARGETS_UNAVAILABLE` | Overall `UNAVAILABLE`. |
| Evaluated instrument universe is empty | `UNAVAILABLE` | `DPM_INSTRUMENT_UNIVERSE_EMPTY` | Overall `UNAVAILABLE`. |
| Eligibility source unavailable | `UNAVAILABLE` | `INSTRUMENT_ELIGIBILITY_UNAVAILABLE` | Overall `UNAVAILABLE`. |
| Tax-lot source unavailable | `UNAVAILABLE` | `PORTFOLIO_TAX_LOTS_UNAVAILABLE` | Overall `UNAVAILABLE`. |
| Market-data source unavailable | `UNAVAILABLE` | `MARKET_DATA_COVERAGE_UNAVAILABLE` | Overall `UNAVAILABLE`. |
| A source product returns `INCOMPLETE` | `INCOMPLETE` | Source-owned reason | Overall `INCOMPLETE` unless another family is `UNAVAILABLE`. |
| A source product returns `DEGRADED` | `DEGRADED` | Source-owned reason | Overall `DEGRADED` unless another family is `UNAVAILABLE` or `INCOMPLETE`. |
| All five families return `READY` | `READY` | Source-owned ready reasons | Overall `READY`. |

Response `data_quality_status` is `COMPLETE` only when the overall supportability state is `READY`;
otherwise it is `PARTIAL`.

## Output Contract Mapping

| Field | Methodology mapping |
| --- | --- |
| `product_name`, `product_version` | Governed source-data product identity. |
| `portfolio_id`, `as_of_date` | Requested readiness scope. |
| `mandate_id`, `model_portfolio_id` | Resolved identifiers when source products return them. |
| `evaluated_instrument_ids` | Sorted unique union of request instruments and model target instruments. |
| `families[]` | One readiness row per source family. |
| `families[].missing_items` | Bounded missing source identifiers or source-family names. |
| `families[].stale_items` | Bounded stale market-data identifiers and FX pairs. |
| `families[].evidence_count` | Source-family count such as target count, resolved eligibility count, tax-lot count, or price/FX observation count. |
| `supportability` | Overall fail-closed state and family-state counts. |
| `lineage.source_system` | Always `lotus-core`. |
| `lineage.contract_version` | Current readiness contract version. |
| `lineage.readiness_scope` | Always `dpm_source_family`. |

## Worked Examples

### Ready DPM Universe

Request:

`POST /integration/portfolios/PB_SG_GLOBAL_BAL_001/dpm-source-readiness`

with as-of date `2026-04-10`, model target instruments `FO_EQ_AAPL_US` and
`FO_BOND_UST_2030`, and currency pair `EUR -> USD`.

| Family | State | Reason | Evidence count |
| --- | --- | --- | ---: |
| `mandate` | `READY` | `MANDATE_BINDING_READY` | 1 |
| `model_targets` | `READY` | `MODEL_TARGETS_READY` | 2 |
| `eligibility` | `READY` | `INSTRUMENT_ELIGIBILITY_READY` | 2 |
| `tax_lots` | `READY` | `TAX_LOTS_READY` | 2 |
| `market_data` | `READY` | `MARKET_DATA_READY` | 3 |

Overall supportability:

| Field | Value |
| --- | --- |
| `state` | `READY` |
| `reason` | `DPM_SOURCE_READINESS_READY` |
| `ready_family_count` | 5 |
| `data_quality_status` | `COMPLETE` |

### Blocked Readiness

If mandate binding and tax lots are unavailable, and market data is missing one price row, the
overall state is `UNAVAILABLE` because unavailable source families outrank incomplete source
families.

| Family | State | Reason |
| --- | --- | --- |
| `mandate` | `UNAVAILABLE` | `MANDATE_BINDING_UNAVAILABLE` |
| `model_targets` | `UNAVAILABLE` | `MODEL_PORTFOLIO_ID_UNAVAILABLE` |
| `eligibility` | `READY` | `INSTRUMENT_ELIGIBILITY_READY` |
| `tax_lots` | `UNAVAILABLE` | `PORTFOLIO_TAX_LOTS_UNAVAILABLE` |
| `market_data` | `INCOMPLETE` | `MARKET_DATA_MISSING` |

Overall supportability:

| Field | Value |
| --- | --- |
| `state` | `UNAVAILABLE` |
| `reason` | `DPM_SOURCE_READINESS_UNAVAILABLE` |
| `unavailable_family_count` | 3 |
| `incomplete_family_count` | 1 |
| `data_quality_status` | `PARTIAL` |

## Downstream Consumption Rule

Downstream applications may use `DpmSourceReadiness:v1` to gate DPM workflow promotion, explain
source-family blockers, and route operators to the missing or stale source family. They must preserve
the family rows and source-owned reason codes.

Downstream applications must not:

1. infer mandate approval or client suitability from readiness alone,
2. recompute model targets, eligibility, tax lots, or market-data coverage locally,
3. treat `READY` as valuation, FX attribution, liquidity, execution, or OMS proof,
4. collapse `UNAVAILABLE`, `INCOMPLETE`, and `DEGRADED` into a generic failure without preserving
   source-family diagnostics,
5. present stale or missing source-family readiness as demo-ready product truth.
