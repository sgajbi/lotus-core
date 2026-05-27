# CR-379: Tax Lot Status Filter Normalization

Date: 2026-05-28

## Scope

Query-service `PortfolioTaxLotWindow` repository filtering for open and closed position lots.

## Finding

`BuyStateRepository.list_portfolio_tax_lots` uppercased `lot_status_filter` without trimming source
whitespace. Padded lower-case values such as ` closed ` could miss the explicit `CLOSED` branch and
fall back to the default open-lot predicate when `include_closed_lots=false`.

This mattered because tax-lot windows are consumed as source-data evidence for discretionary
portfolio management, tax reference evidence, and downstream operational workflows.

## Change

Trimmed lot status filters before uppercase normalization. Added a repository query-shape test
proving padded `closed` compiles to the closed-lot predicate and does not include the open-lot
predicate.

## Evidence

Commands:

1. `python -m pytest tests/unit/services/query_service/repositories/test_buy_state_repository.py -q`
2. `python -m pytest tests/unit/services/query_service/repositories -q`
3. `python -m ruff check src/services/query_service/app/repositories/buy_state_repository.py tests/unit/services/query_service/repositories/test_buy_state_repository.py`

## Closure

Status: Hardened.

No API, OpenAPI, wiki source, or platform contract change was required. This is a repository-query
reliability hardening slice for the existing tax-lot source-data product.
