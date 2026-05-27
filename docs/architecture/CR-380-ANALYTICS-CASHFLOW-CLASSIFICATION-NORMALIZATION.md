# CR-380: Analytics Cashflow Classification Normalization

Date: 2026-05-28

## Scope

Shared analytics cashflow classification helpers and position-timeseries fee aggregation.

## Finding

`portfolio_common.analytics_cashflow_semantics` compared cashflow classifications without trimming
or canonicalizing source values. Position-timeseries fee aggregation also compared `EXPENSE` after
uppercase only. Padded lower-case values such as ` investment_outflow `, ` cashflow_in `, or
` expense ` could:

1. leave investment position-flow signs unnormalized,
2. classify external, internal, income, or fee cashflows as `other`,
3. understate position-timeseries fees.

This mattered because these helpers feed position time series, portfolio time series, and analytics
cashflow observations.

## Change

Trimmed and uppercased cashflow classifications inside the shared analytics cashflow semantics
helpers. Trimmed position-timeseries `EXPENSE` classification before fee aggregation. Added direct
shared-helper tests and position-timeseries tests proving padded lower-case classifications preserve
expected signs, analytics classifications, and fee totals.

## Evidence

Commands:

1. `python -m pytest tests/unit/libs/portfolio-common/test_analytics_cashflow_semantics.py tests/unit/services/timeseries_generator_service/timeseries-generator-service/core/test_position_timeseries_logic.py tests/unit/services/query_service/services/test_analytics_timeseries_service.py -q`
2. `python -m pytest tests/unit/libs/portfolio-common tests/unit/services/timeseries_generator_service/timeseries-generator-service/core tests/unit/services/query_service/services -q`
3. `python -m ruff check src/libs/portfolio-common/portfolio_common/analytics_cashflow_semantics.py src/services/timeseries_generator_service/app/core/position_timeseries_logic.py tests/unit/libs/portfolio-common/test_analytics_cashflow_semantics.py tests/unit/services/timeseries_generator_service/timeseries-generator-service/core/test_position_timeseries_logic.py`

## Closure

Status: Hardened.

No API, OpenAPI, wiki source, or platform contract change was required. This is a shared
calculation-path reliability hardening slice for generated time series and analytics cashflow
observations.
