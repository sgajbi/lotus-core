# CR-1231 Transaction Date Semantic Contract

Date: 2026-07-01

## Objective

Fix GitHub issue #440 by aligning the `TransactionRecord.transaction_date` API/OpenAPI
description with the repository temporal vocabulary and RFC-0083 reconstruction target model.
The slice promotes the reusable pattern that public DTO field descriptions must preserve
canonical temporal meaning and must not relabel legacy/current fields as future target concepts.

## Change

- Changed `TransactionRecord.transaction_date` from `Transaction booking timestamp.` to the
  current supported transaction event timestamp used for trade/event-date filtering and ordering.
- Corrected adjacent `SellDisposalRecord.transaction_date` wording so the shared API vocabulary
  inventory no longer learns transaction-date semantics from a "was booked" description.
- Updated `TransactionRecord.settlement_date` wording to distinguish settlement from the
  transaction event rather than from "trade booking".
- Updated the wealth-reporting API guide so transaction-ledger consumers see the same
  `transaction_date`, `settlement_date`, and future `booking_date` boundary.
- Regenerated the API vocabulary inventory so checked semantic inventory matches DTO source.
- Added OpenAPI regression assertions that fail if transaction-date fields drift back to booking
  terminology.

## Expected Improvement

Downstream consumers no longer receive conflicting public contract guidance for transaction
windows. `transaction_date` remains the current transaction event/trade timestamp for filtering
and latest-first ordering, while `booking_date` remains a future target concept until a dedicated
runtime field and migration plan are introduced.

## Tests Added

- Added `test_openapi_describes_transaction_date_as_event_timestamp` to prove the generated
  query-service OpenAPI schema describes transaction-date fields as transaction event timestamps
  and does not use booking terminology.
- Updated the existing transaction-ledger OpenAPI contract assertion for `settlement_date`.

## Validation Evidence

Initial generation and contract checks:

- API vocabulary inventory regenerated with
  `python scripts/api_vocabulary_inventory.py --output docs/standards/api-vocabulary/lotus-core-api-vocabulary.v1.json`.
- OpenAPI quality gate passed with `python scripts/openapi_quality_gate.py`.
- Generated OpenAPI artifacts under `output/openapi` and `output/openapi-test` were refreshed
  through `scripts.openapi_quality_gate.write_openapi_artifacts(...)` for local evidence.
- Stale wording scan found no remaining `Transaction booking timestamp`, `booked ledger
  date/time`, `Timestamp when the SELL transaction was booked`, or `trade booking from
  contractual` occurrences under `src/services/query_service/app`, `docs/features`,
  `docs/standards`, `output`, or `tests`.

Final focused validation for this commit is recorded in the issue comment and review ledger.

## Downstream Compatibility

No route path, request parameter, response field name, response shape, persistence schema, sort
order, filter behavior, source-data product identity, or runtime behavior changed.

The intentional contract change is documentation/OpenAPI semantics only: consumers should treat
`transaction_date` as the current event/trade timestamp, not as `booking_date`.

## Documentation And Wiki Decision

Updated this architecture record, codebase review ledger, repository context, quality scorecard,
refactor health report, wealth-reporting API guide, and API vocabulary inventory. No repo-local
wiki update is required because no operator command, route navigation, or wiki workflow changed.

## Remaining Follow-Up

- Keep issue #440 open for PR/CI/QA evidence until the branch is reviewed, merged, and validated.
- Future transaction booking work must introduce `booking_date` through an explicit runtime field,
  migration plan, OpenAPI contract, and downstream compatibility review rather than overloading
  `transaction_date`.
