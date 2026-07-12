# CR-373: Liquidity Ladder Control-Code Normalization

Date: 2026-05-28

## Scope

Query-service `PortfolioLiquidityLadder` cash classification, liquidity-tier exposure aggregation,
and response currency metadata.

## Finding

`PortfolioLiquidityLadderService` uppercased asset-class and liquidity-tier values without
trimming source whitespace. Padded lower-case values such as ` cash ` and ` t1 ` could:

1. misclassify cash rows as non-cash holdings,
2. understate opening cash and projected cash availability,
3. overstate non-cash market value,
4. split liquidity-tier exposures across padded aliases,
5. echo non-canonical portfolio currency metadata.

This mattered because liquidity ladder outputs are operational cash-availability and liquidity
supportability calculations.

## Change

Added query-service liquidity ladder control-code normalization that trims and uppercases
asset-class and liquidity-tier values before classification or aggregation. The response
`portfolio_currency` now uses the shared query-service currency normalizer.

## Evidence

Commands:

1. `python -m pytest tests/unit/services/query_service/services/test_liquidity_ladder_service.py -q`
2. `python -m pytest tests/unit/services/query_service/services -q`
3. `python -m ruff check src/services/query_service/app/services/liquidity_ladder_service.py tests/unit/services/query_service/services/test_liquidity_ladder_service.py`

## Closure

Status: Hardened.

No API, OpenAPI, wiki source, or platform contract change was required. This is a calculation-path
reliability hardening slice for the existing liquidity ladder source-data product.
