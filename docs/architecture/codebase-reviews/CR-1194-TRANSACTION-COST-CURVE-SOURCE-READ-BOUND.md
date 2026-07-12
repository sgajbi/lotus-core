# CR-1194: Transaction Cost Curve Source-Read Bound

Date: 2026-06-30

## Objective

Address GitHub issue #681 by making `TransactionCostCurve:v1` cursor paging operationally
truthful at the source-read layer. `page_size` should bound transaction evidence materialization,
not only response shaping after a full-window read.

## Change

- Added a grouped transaction-cost curve keyset query over normalized
  `(security_id, transaction_type, currency)` with `after_key`, `min_observation_count`, and
  `limit=page_size + 1`.
- Added a grouped requested-security coverage query so missing-security supportability can be
  computed without materializing the full transaction evidence window.
- Added an optional `curve_keys` filter to `list_transaction_cost_evidence(...)`; the evidence read
  now returns transaction rows only for selected page keys.
- Updated transaction-cost curve orchestration to skip evidence reads entirely when no eligible page
  keys are returned.
- Updated the transaction-cost curve methodology to document the aggregate keyset read and
  page-scoped transaction evidence read.

## Expected Improvement

Large transaction-cost evidence windows no longer force full transaction plus transaction-cost row
materialization for each page. The endpoint now scales transaction evidence reads with the requested
curve page, while preserving stable cursor identity, deterministic grouping, supportability, and
response shape.

## Tests Added

- Service orchestration tests prove `page_size=1` requests call the keyset query with
  `limit=page_size + 1`, pass selected `curve_keys` into the evidence read, and avoid evidence reads
  when the keyset query is empty.
- Repository SQL-shape tests prove the grouped keyset query applies normalized key ordering,
  `after_key`, `min_observation_count`, filters, and `LIMIT`.
- Repository SQL-shape tests prove requested-security coverage uses a grouped aggregate subquery.
- Repository SQL-shape tests prove evidence reads can be restricted to selected curve keys and skip
  DB execution for an empty key scope.

## Validation Evidence

- `python -m pytest tests/unit/services/query_service/services/test_transaction_cost_curve.py tests/unit/services/query_service/repositories/test_transaction_repository.py -q`
  passed with 47 tests.
- `python -m ruff check src/services/query_service/app/services/transaction_cost_curve.py src/services/query_service/app/repositories/transaction_repository.py tests/unit/services/query_service/services/test_transaction_cost_curve.py tests/unit/services/query_service/repositories/test_transaction_repository.py`
  passed.
- `python -m ruff format --check src/services/query_service/app/services/transaction_cost_curve.py src/services/query_service/app/repositories/transaction_repository.py tests/unit/services/query_service/services/test_transaction_cost_curve.py tests/unit/services/query_service/repositories/test_transaction_repository.py`
  passed.

## Downstream Compatibility

Route path, request DTO fields, response DTO fields, cursor token identity, grouping key, support
states, evidence math, metric formulas, source lineage, and sorted response order are preserved.

The intentional behavior change is operational: transaction evidence rows are fetched only for the
selected page curve keys. The implementation may still run grouped aggregate queries over the
request window to determine eligible keys and requested-security coverage, but it no longer
materializes every transaction row and joined cost row for each page.

## Documentation

- Updated the transaction-cost curve methodology.
- Updated the codebase review ledger.
- Updated the quality scorecard and refactor health report.
- No wiki update required because the repo-local wiki does not carry separate transaction-cost
  curve paging methodology truth; the authored methodology document is the durable source changed
  in this slice.

## Follow-Up

Issue #681 remains open for PR/CI/QA evidence and any production query-plan/index review for large
fee-bearing transaction books. The same source-read budgeting pattern should be considered for
`PerformanceComponentEconomics:v1` under issue #682.
