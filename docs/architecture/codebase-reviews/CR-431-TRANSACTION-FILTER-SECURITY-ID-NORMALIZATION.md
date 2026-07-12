# CR-431: Transaction Filter Security-ID Normalization

Date: 2026-05-28

## Scope

Query-service transaction repository shared filtering for transaction list, count, and latest
evidence timestamp queries.

## Finding

The shared transaction filter helper used raw `security_id` equality for optional security drill
downs. Transaction list, count, and latest-evidence timestamp queries could therefore miss valid
ledger rows when the request identifier and persisted transaction identifier differed only by
padding.

That is a calculation evidence risk because transaction windows are used to explain cashflows,
costs, tax evidence, and ledger-backed analytics inputs.

## Change

Reused the shared query-service security identifier normalizer in
`TransactionRepository._apply_filters(...)`. Optional security filters now trim the request value,
skip blank filters, and compare against `trim(transactions.security_id)` so list, count, and latest
evidence timestamp paths share one canonical filter boundary.

## Evidence

Commands:

1. `python -m pytest tests/unit/services/query_service/repositories/test_transaction_repository.py -q`
2. `python -m ruff check src/services/query_service/app/repositories/transaction_repository.py tests/unit/services/query_service/repositories/test_transaction_repository.py`
3. `python -m pytest tests/unit/services/query_service/repositories -q`
4. `git diff --check`

## Closure

Status: Hardened.

No API route, OpenAPI, wiki source, or platform contract change was required. This is a transaction
evidence hardening slice that prevents source identifier padding from changing ledger visibility or
evidence timestamps.
