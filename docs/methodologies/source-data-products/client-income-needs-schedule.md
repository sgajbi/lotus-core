# Client Income Needs Schedule Methodology

## Metric

`ClientIncomeNeedsSchedule:v1` is the core-owned client income-needs evidence product exposed by
`POST /integration/portfolios/{portfolio_id}/client-income-needs-schedule`.

It returns effective-dated income-needs schedule facts supplied by client master, mandate, or
planning source systems. The product is evidence-only. It is not financial-planning advice, client
liability planning, suitability approval, a funding recommendation, a cashflow forecast, or OMS
acknowledgement.

## Inputs

| Input | Source | Required | Meaning |
| --- | --- | --- | --- |
| `portfolio_id` | Path parameter | Yes | Portfolio whose income-needs evidence is returned. |
| `as_of_date` | Request body | Yes | Effective date for mandate binding and schedule selection. |
| `mandate_id` | Request body | No | Optional mandate discriminator. |
| `tenant_id` | Request body | No | Included in runtime source-data metadata. |
| `include_inactive_schedules` | Request body | No, default `false` | Allows inactive rows to be returned for audit replay. |

## Upstream Data Sources

| Source | Used fields | Inclusion rule |
| --- | --- | --- |
| `portfolio_mandate_bindings` | `portfolio_id`, `client_id`, `mandate_id`, `mandate_type`, `effective_from`, `effective_to`, `observed_at`, `quality_status` | Binding must be discretionary, active, and effective on `as_of_date`. |
| `client_income_needs_schedules` | `client_id`, `portfolio_id`, `mandate_id`, `schedule_id`, `need_type`, `need_status`, `amount`, `currency`, `frequency`, `start_date`, `end_date`, `priority`, `funding_policy`, `source_record_id`, `observed_at`, `quality_status` | Row must match the resolved portfolio and client, be effective on `as_of_date`, and either be mandate-global or match the resolved mandate. |

## Selection Method

1. Resolve `DiscretionaryMandateBinding:v1` for the requested portfolio and `as_of_date`.
2. Return `404` if no active discretionary mandate binding exists.
3. Select effective `client_income_needs_schedules` rows for the resolved `client_id` and portfolio.
4. When `mandate_id` is available, include mandate-global rows and rows for the resolved mandate.
5. Unless `include_inactive_schedules=true`, keep only rows whose `need_status` is `active`.
6. Order by `schedule_id`, latest `start_date`, latest `observed_at`, and latest `updated_at`.
7. Deduplicate to the latest row per `schedule_id`.

## Supportability

| Condition | State | Reason | Missing family |
| --- | --- | --- | --- |
| Binding exists and at least one effective schedule row is returned | `READY` | `CLIENT_INCOME_NEEDS_SCHEDULE_READY` | none |
| Binding exists but no effective schedule row is returned | `INCOMPLETE` | `CLIENT_INCOME_NEEDS_SCHEDULE_EMPTY` | `client_income_needs_schedule` |
| Binding does not exist | HTTP `404` | no response body supportability | n/a |

## Output Semantics

Returned amounts, cadence, priority, and funding policy are source facts for downstream DPM
evidence and proof packs. Consumers must preserve `lineage`, runtime source-data metadata,
`supportability`, and `source_record_id`.
