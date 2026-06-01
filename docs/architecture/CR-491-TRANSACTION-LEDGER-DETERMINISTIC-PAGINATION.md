# CR-491: Transaction Ledger Deterministic Pagination

Date: 2026-05-28

## Scope

Query-service transaction repository ordering for paginated transaction ledger reads.

## Finding

`TransactionRepository.get_transactions(...)` ordered pages only by the requested sort field. The
default ledger order was `transaction_date DESC`, which is business-correct but not deterministic
when multiple booked transactions share the same timestamp. Under offset/limit pagination, rows
with equal sort values could move between pages depending on database plan and concurrent inserts.

The CR-490 index slice added transaction indexes that include `id` as the final ordering key. The
repository query should use the same tie-breaker so the query shape and the index shape stay
aligned.

## Change

Added a deterministic `Transaction.id` tie-breaker to transaction ledger ordering:

1. default latest-first ledger reads now order by `transaction_date DESC, id DESC`,
2. ascending custom sorts tie-break by `id ASC`,
3. descending custom sorts tie-break by `id DESC`.

## Evidence

Commands:

1. `python -m pytest tests/unit/services/query_service/repositories/test_transaction_repository.py -q`
2. `python -m ruff check src/services/query_service/app/repositories/transaction_repository.py tests/unit/services/query_service/repositories/test_transaction_repository.py`
3. `python -m ruff format --check src/services/query_service/app/repositories/transaction_repository.py tests/unit/services/query_service/repositories/test_transaction_repository.py`

Results:

1. Focused transaction repository proof: `25 passed`
2. Touched-surface ruff: passed
3. Touched-surface format check: passed

## Closure

Status: Hardened.

No API route shape, database migration, wiki source, or platform contract change was required. The
transaction ledger now has stable page ordering aligned to the CR-490 transaction date/id index.
