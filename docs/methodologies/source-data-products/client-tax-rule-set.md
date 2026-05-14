# Client Tax Rule Set Methodology

## Metric

`ClientTaxRuleSet:v1` is the core-owned client tax-rule reference evidence product exposed by
`POST /integration/portfolios/{portfolio_id}/client-tax-rule-set`.

It returns effective-dated tax rule references supplied by bank tax or rules source systems. The
product is evidence-only. It is not tax advice, tax-loss harvesting suitability, after-tax
optimization, client-tax approval, jurisdiction-specific recommendation, tax-reporting
certification, best execution, or OMS acknowledgement.

## Endpoint and Mode Coverage

| Request shape | Implemented behavior |
| --- | --- |
| `portfolio_id` path parameter | Selects the portfolio whose client tax rule set is requested. |
| `as_of_date` | Resolves the effective discretionary mandate binding and rule records. |
| optional `mandate_id` | Disambiguates the mandate binding when supplied. |
| optional `tenant_id` | Carried into runtime source-data metadata. |
| `include_inactive_rules=false` | Returns only active effective rule rows. |
| `include_inactive_rules=true` | Includes inactive or suspended effective rows for audit replay. |

The product currently has one implemented methodology: bounded source-record exposure from
`client_tax_rule_sets`. It does not calculate tax due, choose securities to sell, determine wash-sale
treatment, or recommend client tax actions.

## Inputs

| Input | Source | Required | Meaning |
| --- | --- | --- | --- |
| `portfolio_id` | Path parameter | Yes | Portfolio whose tax rule evidence is returned. |
| `as_of_date` | Request body | Yes | Effective date for mandate binding and rule selection. |
| `mandate_id` | Request body | No | Optional mandate discriminator. |
| `tenant_id` | Request body | No | Included in runtime source-data metadata. |
| `include_inactive_rules` | Request body | No, default `false` | Allows inactive and suspended rows to be returned for audit replay. |

## Upstream Data Sources

| Source | Used fields | Inclusion rule |
| --- | --- | --- |
| `portfolio_mandate_bindings` | `portfolio_id`, `client_id`, `mandate_id`, `mandate_type`, `discretionary_authority_status`, `effective_from`, `effective_to`, `observed_at`, `quality_status` | Binding must be discretionary, active, and effective on `as_of_date`. |
| `client_tax_rule_sets` | `client_id`, `portfolio_id`, `mandate_id`, `rule_set_id`, `tax_year`, `jurisdiction_code`, `rule_code`, `rule_category`, `rule_status`, `rule_source`, `applies_to_asset_classes`, `applies_to_security_ids`, `applies_to_income_types`, `rate`, `threshold_amount`, `threshold_currency`, `effective_from`, `effective_to`, `rule_version`, `source_record_id`, `observed_at`, `quality_status` | Row must match the resolved portfolio and client, be effective on `as_of_date`, and either be mandate-global or match the resolved mandate. |

## Selection Method

1. Resolve `DiscretionaryMandateBinding:v1` for the requested portfolio and `as_of_date`.
2. Return `404` if no active discretionary mandate binding exists.
3. Select effective `client_tax_rule_sets` rows for the resolved `client_id` and portfolio.
4. When `mandate_id` is available, include mandate-global rows and rows for the resolved mandate.
5. Unless `include_inactive_rules=true`, keep only rows whose `rule_status` is `active`.
6. Order by `rule_set_id`, `jurisdiction_code`, `rule_code`, latest `effective_from`, latest
   `observed_at`, highest `rule_version`, and latest `updated_at`.
7. Deduplicate to the latest row per `rule_set_id`, `jurisdiction_code`, and `rule_code`.

## Supportability

| Condition | State | Reason | Missing family |
| --- | --- | --- | --- |
| Binding exists and at least one effective rule row is returned | `READY` | `CLIENT_TAX_RULE_SET_READY` | none |
| Binding exists but no effective rule row is returned | `INCOMPLETE` | `CLIENT_TAX_RULE_SET_EMPTY` | `client_tax_rule_set` |
| Binding does not exist | HTTP `404` | no response body supportability | n/a |

## Output Semantics

Returned rates and thresholds are source-supplied references. Applicability lists constrain the
source rule evidence by asset class, security id, or income type. A missing rule row means missing
evidence, not permission to infer a zero rate or client approval.

Consumers must preserve `lineage`, runtime source-data metadata, `supportability`, and
`source_record_id` when using the product as DPM evidence.
