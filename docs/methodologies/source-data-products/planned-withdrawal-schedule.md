# Planned Withdrawal Schedule Methodology

## Metric

`PlannedWithdrawalSchedule:v1` is the core-owned planned-withdrawal evidence product exposed by
`POST /integration/portfolios/{portfolio_id}/planned-withdrawal-schedule`.

It returns planned withdrawal records supplied by mandate, client master, or planning source
systems over a requested forward horizon. The product is evidence-only. It is not a cashflow
forecast, financial-planning advice, suitability approval, funding recommendation, treasury
instruction, or OMS acknowledgement.

## Inputs

| Input | Source | Required | Meaning |
| --- | --- | --- | --- |
| `portfolio_id` | Path parameter | Yes | Portfolio whose planned withdrawal evidence is returned. |
| `as_of_date` | Request body | Yes | Lower bound for planned withdrawal selection. |
| `horizon_days` | Request body | No, default `365` | Forward calendar-day window, inclusive of the end date. |
| `mandate_id` | Request body | No | Optional mandate discriminator. |
| `tenant_id` | Request body | No | Included in runtime source-data metadata. |
| `include_inactive_withdrawals` | Request body | No, default `false` | Allows inactive rows to be returned for audit replay. |

## Upstream Data Sources

| Source | Used fields | Inclusion rule |
| --- | --- | --- |
| `portfolio_mandate_bindings` | `portfolio_id`, `client_id`, `mandate_id`, `mandate_type`, `effective_from`, `effective_to`, `observed_at`, `quality_status` | Binding must be discretionary, active, and effective on `as_of_date`. |
| `planned_withdrawal_schedules` | `client_id`, `portfolio_id`, `mandate_id`, `withdrawal_schedule_id`, `withdrawal_type`, `withdrawal_status`, `amount`, `currency`, `scheduled_date`, `recurrence_frequency`, `purpose_code`, `source_record_id`, `observed_at`, `quality_status` | Row must match the resolved portfolio and client, have `scheduled_date` within `[as_of_date, as_of_date + horizon_days]`, and either be mandate-global or match the resolved mandate. |

## Selection Method

1. Resolve `DiscretionaryMandateBinding:v1` for the requested portfolio and `as_of_date`.
2. Return `404` if no active discretionary mandate binding exists.
3. Select `planned_withdrawal_schedules` rows for the resolved `client_id`, portfolio, and horizon.
4. When `mandate_id` is available, include mandate-global rows and rows for the resolved mandate.
5. Unless `include_inactive_withdrawals=true`, keep only rows whose `withdrawal_status` is `active`.
6. Order by `scheduled_date`, `withdrawal_schedule_id`, latest `observed_at`, and latest `updated_at`.
7. Deduplicate to the latest row per `withdrawal_schedule_id` and `scheduled_date`.

## Supportability

| Condition | State | Reason | Missing family |
| --- | --- | --- | --- |
| Binding exists and at least one planned withdrawal row is returned | `READY` | `PLANNED_WITHDRAWAL_SCHEDULE_READY` | none |
| Binding exists but no planned withdrawal row is returned | `INCOMPLETE` | `PLANNED_WITHDRAWAL_SCHEDULE_EMPTY` | `planned_withdrawal_schedule` |
| Binding does not exist | HTTP `404` | no response body supportability | n/a |

## Output Semantics

Returned withdrawal amounts, dates, recurrence, and purpose codes are source facts for downstream
DPM evidence and proof packs. Consumers must preserve `lineage`, runtime source-data metadata,
`supportability`, and `source_record_id`.
