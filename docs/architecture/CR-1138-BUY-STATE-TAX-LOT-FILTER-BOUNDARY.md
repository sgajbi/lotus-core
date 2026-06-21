# CR-1138 Buy-State Tax-Lot Filter Boundary

Date: 2026-06-22

## Scope

Portfolio tax-lot source reads in
`src/services/query_service/app/repositories/buy_state_repository.py`.

## Finding

`BuyStateRepository.list_portfolio_tax_lots(...)` owned portfolio/as-of filtering, optional
security normalization, unsupported blank-security posture, open/closed lot status selection,
keyset pagination, transaction-currency enrichment, ordering, and limit behavior in one C-ranked
repository method. This method backs DPM tax-lot source readiness and portfolio tax-lot window
evidence, so filter posture needs to stay easy to review.

Radon reported:

- `BuyStateRepository.list_portfolio_tax_lots`: `C (11)`

## Action Taken

Extracted focused helpers for:

- security-scope normalization,
- lot-status normalization and open/closed predicate selection,
- acquisition-date/lot-id keyset pagination,
- optional predicate appending.

Added direct unit coverage proving blank normalized security scopes return no rows without a DB
query and keyset pagination emits the expected acquisition-date/lot-id predicates.

## Evidence

Focused behavior proof:

- `python -m pytest tests\unit\services\query_service\repositories\test_buy_state_repository.py -q`
- Result: `10 passed`

Focused static proof:

- `python -m ruff check src/services/query_service/app/repositories/buy_state_repository.py tests/unit/services/query_service/repositories/test_buy_state_repository.py`
- Result: passed

Focused format proof:

- `python -m ruff format --check src/services/query_service/app/repositories/buy_state_repository.py tests/unit/services/query_service/repositories/test_buy_state_repository.py`
- Result: passed

Focused complexity proof:

- `python -m radon cc src/services/query_service/app/repositories/buy_state_repository.py -s --exclude "*/build/*"`
- Result: `BuyStateRepository.list_portfolio_tax_lots` is `A (4)`, and every function/class in
  `buy_state_repository.py` is A-ranked.

Measured movement:

- `BuyStateRepository.list_portfolio_tax_lots`: `C (11)` -> `A (4)`

## Residual Risk

This slice does not change the portfolio tax-lot route, DPM source-product semantics,
OpenAPI descriptions, page ordering, lot-status names, or transaction-currency enrichment. Broader
portfolio tax-lot supportability and DPM integration behavior remain covered by their existing
service/integration tests.

## Bank-Buyable Control Movement

This slice improves:

- reviewability of governed tax-lot source filtering,
- direct proof for no-query blank-security posture,
- deterministic proof for keyset pagination predicates.

It does not claim full bank-buyable readiness for `lotus-core`.
