# CR-366: Query-Service FX Range Lookup Currency Normalization

Date: 2026-05-28

## Scope

Query-service FX range lookup repositories used by analytics timeseries, reference-data, and raw
FX-rate query paths.

## Finding

Several query-service FX range lookup paths still used raw caller currency codes, or only
`upper()` without trimming source whitespace:

1. `AnalyticsTimeseriesRepository.get_fx_rates_map(...)`,
2. `ReferenceDataRepository.get_fx_rates(...)`,
3. `ReferenceDataRepository.list_latest_fx_rates(...)`,
4. `FxRateRepository.get_fx_rates(...)`.

Padded or lower-case currency values could miss canonical FX rows, fragment downstream conversion
behavior, or require avoidable retry/fallback behavior even when bank-owned reference data was
present.

## Change

Reused the shared query-service repository `normalize_currency_code(...)` helper for all affected
range lookup paths. Normalization happens before building SQL predicates, so queries still compare
canonical constants directly to `FxRate.from_currency` and `FxRate.to_currency`; no column-side
functions were introduced.

Updated repository tests to pass padded lower-case currency values and assert canonical SQL
predicates for analytics timeseries, reference-data, and raw FX-rate query paths.

## Evidence

Commands:

1. `python -m pytest tests/unit/services/query_service/repositories/test_analytics_timeseries_repository.py tests/unit/services/query_service/repositories/test_reference_data_repository.py tests/unit/services/query_service/repositories/test_fx_rate_repository.py -q`
2. `python -m pytest tests/unit/services/query_service/repositories -q`
3. `python -m ruff check src/services/query_service/app/repositories/analytics_timeseries_repository.py src/services/query_service/app/repositories/reference_data_repository.py src/services/query_service/app/repositories/fx_rate_repository.py tests/unit/services/query_service/repositories/test_analytics_timeseries_repository.py tests/unit/services/query_service/repositories/test_reference_data_repository.py tests/unit/services/query_service/repositories/test_fx_rate_repository.py`

## Closure

Status: Hardened.

No API, OpenAPI, wiki source, or platform contract change was required. This is a repository-level
calculation reliability and query-efficiency hardening slice for canonical FX-rate range retrieval.
