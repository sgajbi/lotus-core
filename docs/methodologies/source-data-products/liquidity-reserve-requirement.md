# Liquidity Reserve Requirement Methodology

## Metric

`LiquidityReserveRequirement:v1` is the core-owned liquidity-reserve requirement evidence product
exposed by `POST /integration/portfolios/{portfolio_id}/liquidity-reserve-requirement`.

It returns effective-dated reserve requirement facts supplied by mandate, treasury, or policy source
systems. The product is evidence-only. It is not financial-planning advice, suitability approval, a
cash reserve recommendation, a treasury instruction, or OMS acknowledgement.

## Inputs

| Input | Source | Required | Meaning |
| --- | --- | --- | --- |
| `portfolio_id` | Path parameter | Yes | Portfolio whose reserve evidence is returned. |
| `as_of_date` | Request body | Yes | Effective date for mandate binding and requirement selection. |
| `mandate_id` | Request body | No | Optional mandate discriminator. |
| `tenant_id` | Request body | No | Included in runtime source-data metadata. |
| `include_inactive_requirements` | Request body | No, default `false` | Allows inactive rows to be returned for audit replay. |

## Upstream Data Sources

| Source | Used fields | Inclusion rule |
| --- | --- | --- |
| `portfolio_mandate_bindings` | `portfolio_id`, `client_id`, `mandate_id`, `mandate_type`, `effective_from`, `effective_to`, `observed_at`, `quality_status` | Binding must be discretionary, active, and effective on `as_of_date`. |
| `liquidity_reserve_requirements` | `client_id`, `portfolio_id`, `mandate_id`, `reserve_requirement_id`, `reserve_type`, `reserve_status`, `required_amount`, `currency`, `horizon_days`, `priority`, `policy_source`, `effective_from`, `effective_to`, `requirement_version`, `source_record_id`, `observed_at`, `quality_status` | Row must match the resolved portfolio and client, be effective on `as_of_date`, and either be mandate-global or match the resolved mandate. |

## Selection Method

1. Resolve `DiscretionaryMandateBinding:v1` for the requested portfolio and `as_of_date`.
2. Return `404` if no active discretionary mandate binding exists.
3. Select effective `liquidity_reserve_requirements` rows for the resolved `client_id` and portfolio.
4. When `mandate_id` is available, include mandate-global rows and rows for the resolved mandate.
5. Unless `include_inactive_requirements=true`, keep only rows whose `reserve_status` is `active`.
6. Order by `reserve_requirement_id`, latest `effective_from`, latest `observed_at`, highest
   `requirement_version`, and latest `updated_at`.
7. Deduplicate to the latest row per `reserve_requirement_id`.

## Supportability

| Condition | State | Reason | Missing family |
| --- | --- | --- | --- |
| Binding exists and at least one effective requirement row is returned | `READY` | `LIQUIDITY_RESERVE_REQUIREMENT_READY` | none |
| Binding exists but no effective requirement row is returned | `INCOMPLETE` | `LIQUIDITY_RESERVE_REQUIREMENT_EMPTY` | `liquidity_reserve_requirement` |
| Binding does not exist | HTTP `404` | no response body supportability | n/a |

## Output Semantics

Returned reserve amounts, horizons, priority, and policy source are source facts for downstream DPM
evidence and proof packs. Consumers must preserve `lineage`, runtime source-data metadata,
`supportability`, and `source_record_id`.
