# CR-364: Valuation Repository FX Currency Normalization

Date: 2026-05-27

## Scope

Position valuation calculator repository FX lookup boundary.

## Finding

`ValuationRepositoryBase.get_fx_rate(...)` compared caller-provided `from_currency` and
`to_currency` values directly against persisted FX-rate rows. The valuation consumer and valuation
logic now normalize calculation currency inputs, but the repository boundary still trusted every
caller to provide canonical currency codes.

That left a durable lookup edge where padded or lower-case source values could miss an available FX
rate, causing a valuation job to fail as missing FX even though the bank-owned reference data was
present.

## Change

Added repository-local currency normalization using `strip().upper()` before building the FX-rate
query. The query still compares normalized constants directly against `FxRate.from_currency` and
`FxRate.to_currency`, preserving the index-friendly equality predicate rather than pushing
normalization functions onto table columns.

Added a query-shape unit proof that padded lower-case inputs compile into canonical `EUR` to `USD`
currency predicates with the existing latest-rate date fence and descending rate-date ordering.

## Evidence

Commands:

1. `python -m pytest tests/unit/services/calculators/position_valuation_calculator/repositories/test_valuation_repository_worker_metrics.py -q`
2. `python -m pytest tests/unit/services/calculators/position_valuation_calculator -q`
3. `python -m ruff check src/libs/portfolio-common/portfolio_common/valuation_repository_base.py tests/unit/services/calculators/position_valuation_calculator/repositories/test_valuation_repository_worker_metrics.py`

## Closure

Status: Hardened.

No API, OpenAPI, wiki source, or platform contract change was required. This is a defensive
calculation-path hardening slice for repository lookup reliability and index-friendly FX-rate
retrieval.
