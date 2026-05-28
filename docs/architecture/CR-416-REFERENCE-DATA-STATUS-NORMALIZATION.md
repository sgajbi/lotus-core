# CR-416: Reference Data Status Normalization

Date: 2026-05-28

## Scope

Query-service reference-data repository status predicates for effective-dated model portfolio,
mandate, client restriction, sustainability, tax, income, liquidity, withdrawal, benchmark, and
index source-data rows.

## Finding

Reference-data source-product queries filtered approved or active rows with direct persisted string
comparisons. Casing or whitespace drift could exclude valid model portfolio definitions, targets,
discretionary mandate bindings, client restrictions, sustainability preferences, tax profiles,
income needs, liquidity reserves, planned withdrawals, benchmark definitions, or index definitions
from Core's authoritative source-data products. Those omissions can propagate into DPM readiness,
portfolio universe selection, proposal simulation inputs, and analytics supportability.

## Change

Added shared reference-status normalization using `lower(trim(...))` and normalized optional
caller-provided benchmark/index status filters. Reused the normalized predicate across the
reference-data repository's approved/active status gates. Updated query-shape tests for model
portfolio definition, model targets, affected mandate selection, DPM universe candidates, and
inactive bypass behavior.

## Evidence

Commands:

1. `python -m pytest tests/unit/services/query_service/repositories/test_reference_data_repository.py -q`
2. `python -m pytest tests/unit/services/query_service/repositories -q`
3. `python -m ruff check src/services/query_service/app/repositories/reference_data_repository.py tests/unit/services/query_service/repositories/test_reference_data_repository.py`

## Closure

Status: Hardened.

No API route, OpenAPI, wiki source, or platform contract change was required. This is an internal
query repository reliability slice that keeps effective-dated source-data products stable when
persisted reference-data status control codes drift.
