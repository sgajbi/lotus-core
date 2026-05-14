# Client Tax Profile Methodology

## Metric

`ClientTaxProfile:v1` is the core-owned client tax-reference evidence product exposed by
`POST /integration/portfolios/{portfolio_id}/client-tax-profile`.

It returns effective-dated tax profile facts supplied by bank tax, client master, or mandate source
systems. The product is evidence-only. It is not tax advice, after-tax optimization, tax-loss
harvesting suitability, client-tax approval, jurisdiction-specific recommendation, tax-reporting
certification, or OMS acknowledgement.

## Endpoint and Mode Coverage

| Request shape | Implemented behavior |
| --- | --- |
| `portfolio_id` path parameter | Selects the portfolio whose client tax profile is requested. |
| `as_of_date` | Resolves the effective discretionary mandate binding and profile records. |
| optional `mandate_id` | Disambiguates the mandate binding when supplied. |
| optional `tenant_id` | Carried into runtime source-data metadata. |
| `include_inactive_profiles=false` | Returns only active effective profile rows. |
| `include_inactive_profiles=true` | Includes inactive or suspended effective rows for audit replay. |

The product currently has one implemented methodology: bounded source-record exposure from
`client_tax_profiles`. It does not calculate taxes, derive effective tax rates, choose tax lots, or
approve any client tax outcome.

## Inputs

| Input | Source | Required | Meaning |
| --- | --- | --- | --- |
| `portfolio_id` | Path parameter | Yes | Portfolio whose tax profile evidence is returned. |
| `as_of_date` | Request body | Yes | Effective date for mandate binding and profile selection. |
| `mandate_id` | Request body | No | Optional mandate discriminator. |
| `tenant_id` | Request body | No | Included in runtime source-data metadata. |
| `include_inactive_profiles` | Request body | No, default `false` | Allows inactive and suspended rows to be returned for audit replay. |

## Upstream Data Sources

| Source | Used fields | Inclusion rule |
| --- | --- | --- |
| `portfolio_mandate_bindings` | `portfolio_id`, `client_id`, `mandate_id`, `mandate_type`, `discretionary_authority_status`, `effective_from`, `effective_to`, `observed_at`, `quality_status` | Binding must be discretionary, active, and effective on `as_of_date`. |
| `client_tax_profiles` | `client_id`, `portfolio_id`, `mandate_id`, `tax_profile_id`, `tax_residency_country`, `booking_tax_jurisdiction`, `tax_status`, `profile_status`, `withholding_tax_rate`, `capital_gains_tax_applicable`, `income_tax_applicable`, `treaty_codes`, `eligible_account_types`, `effective_from`, `effective_to`, `profile_version`, `source_record_id`, `observed_at`, `quality_status` | Row must match the resolved portfolio and client, be effective on `as_of_date`, and either be mandate-global or match the resolved mandate. |

## Selection Method

1. Resolve `DiscretionaryMandateBinding:v1` for the requested portfolio and `as_of_date`.
2. Return `404` if no active discretionary mandate binding exists.
3. Select effective `client_tax_profiles` rows for the resolved `client_id` and portfolio.
4. When `mandate_id` is available, include mandate-global rows and rows for the resolved mandate.
5. Unless `include_inactive_profiles=true`, keep only rows whose `profile_status` is `active`.
6. Order by `tax_profile_id`, latest `effective_from`, latest `observed_at`, highest
   `profile_version`, and latest `updated_at`.
7. Deduplicate to the latest row per `tax_profile_id`.

## Supportability

| Condition | State | Reason | Missing family |
| --- | --- | --- | --- |
| Binding exists and at least one effective profile row is returned | `READY` | `CLIENT_TAX_PROFILE_READY` | none |
| Binding exists but no effective profile row is returned | `INCOMPLETE` | `CLIENT_TAX_PROFILE_EMPTY` | `client_tax_profile` |
| Binding does not exist | HTTP `404` | no response body supportability | n/a |

## Output Semantics

Returned `withholding_tax_rate` is a source-supplied reference ratio. Boolean tax-applicability
fields are source facts only. Treaty and eligible-account lists are bounded source codes for
downstream evidence and proof packs.

Consumers must preserve `lineage`, runtime source-data metadata, `supportability`, and
`source_record_id` when using the product as DPM evidence.
