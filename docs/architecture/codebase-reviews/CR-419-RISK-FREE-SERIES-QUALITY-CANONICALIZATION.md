# CR-419: Risk-Free Series Quality Canonicalization

Date: 2026-05-28

## Scope

Shared market/reference quality helpers, query-service reference-data repository benchmark and
risk-free coverage quality metadata, benchmark market-series quality summaries, and risk-free
duplicate-date canonicalization.

## Finding

Risk-free series duplicate-date selection sorted accepted observations ahead of lower-quality rows
and then overwrote the selected row by date. A lower-quality duplicate with a later source timestamp
or higher deterministic tie-breaker could therefore replace an accepted observation for the same
date. That can feed the wrong risk-free point into downstream return, excess-return, and risk
calculation inputs.

Reference coverage quality counts and benchmark market-series quality summaries also used raw
persisted quality status values. Case, whitespace, or missing quality codes could fragment metadata
such as `accepted`, `STALE`, and blank values instead of presenting a stable data-product quality
signal.

## Change

Promoted public shared quality-status helpers in `portfolio_common.market_reference_quality`.
Repository coverage counts and benchmark market-series quality summaries now use the same
summary-key normalization. Risk-free duplicate-date canonicalization now uses the shared canonical
quality status so accepted observations win even when persisted quality status has case or
whitespace drift, while preserving deterministic timestamp and source tie-breakers inside the
selected quality tier.

## Evidence

Commands:

1. `python -m pytest tests/unit/services/query_service/repositories/test_reference_data_repository.py -q`
2. `python -m pytest tests/unit/services/query_service/repositories -q`
3. `python -m pytest tests/unit/libs/portfolio-common/test_market_reference_quality.py -q`
4. `python -m pytest tests/unit/services/query_service/services/test_integration_service.py -q`
5. `python -m ruff check src/libs/portfolio-common/portfolio_common/market_reference_quality.py src/services/query_service/app/repositories/reference_data_repository.py src/services/query_service/app/services/integration_service.py tests/unit/libs/portfolio-common/test_market_reference_quality.py tests/unit/services/query_service/repositories/test_reference_data_repository.py tests/unit/services/query_service/services/test_integration_service.py`

## Closure

Status: Hardened.

No API route, OpenAPI, wiki source, or platform contract change was required. This is an internal
market/reference correctness slice that stabilizes risk-free calculation inputs and source-data
quality metadata keys without changing the public contract shape.
