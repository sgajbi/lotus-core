# CR-419: Risk-Free Series Quality Canonicalization

Date: 2026-05-28

## Scope

Query-service reference-data repository benchmark and risk-free coverage quality metadata, plus
risk-free duplicate-date canonicalization.

## Finding

Risk-free series duplicate-date selection sorted accepted observations ahead of lower-quality rows
and then overwrote the selected row by date. A lower-quality duplicate with a later source timestamp
or higher deterministic tie-breaker could therefore replace an accepted observation for the same
date. That can feed the wrong risk-free point into downstream return, excess-return, and risk
calculation inputs.

Reference coverage quality counts also used raw persisted quality status values. Case, whitespace,
or missing quality codes could fragment coverage metadata such as `accepted`, `STALE`, and blank
values instead of presenting a stable data-product quality signal.

## Change

Added a repository-level quality-status normalizer that trims, lower-cases, and maps blank values to
`unknown`. Reused it for benchmark and risk-free coverage quality-count metadata. Updated risk-free
duplicate-date canonicalization so accepted observations win even when persisted quality status has
case or whitespace drift, while preserving deterministic timestamp and source tie-breakers inside
the selected quality tier.

## Evidence

Commands:

1. `python -m pytest tests/unit/services/query_service/repositories/test_reference_data_repository.py -q`
2. `python -m pytest tests/unit/services/query_service/repositories -q`
3. `python -m ruff check src/services/query_service/app/repositories/reference_data_repository.py tests/unit/services/query_service/repositories/test_reference_data_repository.py`

## Closure

Status: Hardened.

No API route, OpenAPI, wiki source, or platform contract change was required. This is an internal
reference-data correctness slice that stabilizes risk-free calculation inputs and source-data
quality metadata without changing the public contract shape.
