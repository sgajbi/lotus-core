# CR-420: Market Reference Series Duplicate-Date Canonicalization

Date: 2026-05-28

## Scope

Query-service reference-data repository index price, index return, benchmark return, and risk-free
series query boundaries.

## Finding

Index price, index return, benchmark return, and risk-free series tables can contain multiple
source-series rows for the same business key and `series_date` because `series_id` is part of the
database uniqueness contract. Several downstream paths consume those rows as business-date series
and later collapse them by index/date or benchmark/date. Without canonicalization at the repository
boundary, a lower-quality duplicate could override an accepted observation depending on database
row order, source timestamp, or source-series identity.

That drift can affect benchmark market-series responses, coverage evidence, excess-return inputs,
and downstream performance or risk calculations that need stable market/reference inputs.

## Change

Replaced the risk-free-only duplicate-date selector with a reusable repository helper for
market/reference series rows. The helper selects one row per business key and `series_date`,
prefers accepted observations using the shared market/reference quality normalizer, and then uses
deterministic timestamp and source identity tie-breakers inside the selected quality tier.

Applied the helper to:

1. index price points,
2. index return points,
3. benchmark return points,
4. single-index price series,
5. single-index return series,
6. risk-free series.

## Evidence

Commands:

1. `python -m pytest tests/unit/services/query_service/repositories/test_reference_data_repository.py -q`
2. `python -m pytest tests/unit/services/query_service/repositories -q`
3. `python -m ruff check src/services/query_service/app/repositories/reference_data_repository.py tests/unit/services/query_service/repositories/test_reference_data_repository.py`

## Closure

Status: Hardened.

No API route, OpenAPI, wiki source, or platform contract change was required. This is an internal
reference-data query-boundary correctness slice that stabilizes calculation inputs without changing
the public contract shape.
