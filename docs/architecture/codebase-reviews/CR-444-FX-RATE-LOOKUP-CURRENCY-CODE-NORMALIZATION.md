# CR-444: FX Rate Lookup Currency-Code Normalization

Date: 2026-05-28

## Scope

Query-service FX rate lookup repositories and the FX-rate lookup index used by private-banking
valuation, reporting, analytics timeseries, reference-data integration, and raw FX history APIs.

## Finding

Several query-service FX lookup paths normalized caller-supplied currency codes but compared them
against persisted `fx_rates.from_currency` and `fx_rates.to_currency` values as raw strings. Lower
case or padded source-owned FX rows could therefore be invisible to valuation, reporting, analytics,
and integration calculations even when the required rate existed.

That is a calculation-correctness and supportability risk: missing FX data can block valuation,
distort reporting coverage, fragment analytics evidence, or create false data-quality defects.

## Change

Added a shared repository SQL expression for canonical currency-code comparisons and applied it to
FX-rate lookup predicates in:

1. `FxRateRepository.get_fx_rates(...)`
2. `AnalyticsTimeseriesRepository.get_fx_rates_map(...)`
3. `ReferenceDataRepository.get_fx_rates(...)`
4. `ReferenceDataRepository.list_latest_fx_rates(...)`
5. `ReportingRepository.get_latest_fx_rate(...)`
6. `TransactionRepository.get_latest_fx_rate(...)`

Added a normalized FX-rate lookup index to the model and Alembic migration chain so the corrected
query shape has an explicit production performance posture:

`ix_fx_rates_normalized_pair_rate_date`

## Evidence

Commands:

1. `python -m pytest tests/unit/services/query_service/repositories/test_fx_rate_repository.py tests/unit/services/query_service/repositories/test_analytics_timeseries_repository.py tests/unit/services/query_service/repositories/test_reference_data_repository.py tests/unit/services/query_service/repositories/test_reporting_repository.py tests/unit/services/query_service/repositories/test_transaction_repository.py -q`
2. `python -m ruff check alembic/versions/8a9b0c1d2e3f_perf_add_normalized_fx_rate_lookup_index.py src/libs/portfolio-common/portfolio_common/database_models.py src/services/query_service/app/repositories/currency_codes.py src/services/query_service/app/repositories/fx_rate_repository.py src/services/query_service/app/repositories/analytics_timeseries_repository.py src/services/query_service/app/repositories/reference_data_repository.py src/services/query_service/app/repositories/reporting_repository.py src/services/query_service/app/repositories/transaction_repository.py tests/unit/services/query_service/repositories/test_fx_rate_repository.py tests/unit/services/query_service/repositories/test_analytics_timeseries_repository.py tests/unit/services/query_service/repositories/test_reference_data_repository.py tests/unit/services/query_service/repositories/test_reporting_repository.py tests/unit/services/query_service/repositories/test_transaction_repository.py`
3. `python -m alembic heads`
4. `python -m pytest tests/unit/services/query_service/repositories -q`
5. `python -m pytest tests/unit/services/query_service/services -q`
6. `git diff --check`

Results:

1. Focused repository pytest: `72 passed`
2. Touched-surface ruff: passed
3. Alembic head: `8a9b0c1d2e3f`
4. Broader query-service repository pack: `209 passed`
5. Broader query-service service pack: `456 passed`
6. Diff hygiene: passed

## Closure

Status: Hardened.

No API route, OpenAPI, wiki source, or platform contract change was required. This is a
calculation-correctness and production-query-shape hardening slice that prevents FX reference-data
format drift from hiding available rates while adding the database index needed for scalable lookup.
