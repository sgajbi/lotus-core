# CR-1137 Transaction Repository Filter Boundary

Date: 2026-06-22

## Scope

Transaction read filtering in
`src/services/query_service/app/repositories/transaction_repository.py`.

## Finding

`TransactionRepository._apply_filters(...)` owned portfolio scoping, optional instrument and
transaction identity filters, normalized security filtering, inclusive start-date behavior,
exclusive end-date behavior, and as-of-date behavior in one C-ranked branch chain. The helper is
shared by transaction list, count, cost-evidence, performance-component economics, and realized-tax
evidence reads, so filter reviewability matters for downstream portfolio evidence reliability.

Radon reported:

- `TransactionRepository._apply_filters`: `C (14)`

## Action Taken

Extracted focused helpers for:

- identity filter keyword construction,
- normalized security filtering,
- transaction-date boundary filtering.

Added focused count-query coverage proving identity filters and date boundaries still apply through
the shared filter path, not only through the paginated transaction-list query.

## Evidence

Focused behavior proof:

- `python -m pytest tests\unit\services\query_service\repositories\test_transaction_repository.py -q`
- Result: `27 passed`

Focused static proof:

- `python -m ruff check src/services/query_service/app/repositories/transaction_repository.py tests/unit/services/query_service/repositories/test_transaction_repository.py`
- Result: passed

Focused complexity proof:

- `python -m radon cc src/services/query_service/app/repositories/transaction_repository.py -s --exclude "*/build/*"`
- Result: `TransactionRepository._apply_filters` is `A (1)`.

Measured movement:

- `TransactionRepository._apply_filters`: `C (14)` -> `A (1)`

## Residual Risk

This slice does not change route contracts, transaction filter names, sort behavior, pagination,
OpenAPI descriptions, or downstream source-product semantics. It preserves the existing in-memory
SQLAlchemy query construction pattern and does not claim broader transaction-domain completeness.

## Bank-Buyable Control Movement

This slice improves:

- reviewability of shared transaction evidence filtering,
- deterministic coverage for count-query filter behavior,
- lower branch complexity in a portfolio evidence repository boundary.

It does not claim full bank-buyable readiness for `lotus-core`.
