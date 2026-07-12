# CR-111 Reprocessing Request Ordering Review

## Scope

- `src/libs/portfolio-common/portfolio_common/reprocessing_repository.py`
- `tests/unit/libs/portfolio-common/test_reprocessing_repository.py`

## Finding

`ReprocessingRepository.reprocess_transactions_by_ids(...)` fetched rows with
`WHERE transaction_id IN (...)` and no `ORDER BY`.

That is nondeterministic for multi-transaction replay requests. It is acceptable
for a one-id consumer path, but it is not acceptable for a reusable replay API
that accepts an ordered list of transaction ids.

## Action Taken

- Added explicit ordering by caller-provided `transaction_ids`
- Added a unit test proving publication order matches request order

## Result

Multi-transaction replay requests now preserve caller intent deterministically
instead of depending on database row-return order.
