# CR-1255 Transaction Persistence Instrument Policy

Date: 2026-07-01

## Objective

Close the remaining local scope of GitHub issue #674 by making the transaction persistence boundary
explicit about unresolved instrument references. Earlier #674 slices stopped product lifecycle
processing before cost and BUY lot-state writes when instrument master data is missing, then added
read-side degraded supportability for transaction ledger and tax-lot source products. This slice
documents and tests the raw persistence policy so unresolved references are no longer silent normal
rows at the landing boundary.

## Change

- Added `transaction_instrument_policy.py` for raw transaction instrument-reference decisions.
- Added repository `check_instrument_exists(...)` against governed `instruments.security_id` master
  data.
- Routed `TransactionPersistenceConsumer` through the policy before raw transaction UPSERT.
- Preserved raw transaction landing for unresolved instruments as
  `provisional_raw_landing`, because transaction and instrument events can arrive in separate
  source batches.
- Added source-safe structured operational evidence with reason
  `TRANSACTION_INSTRUMENT_REFERENCE_PENDING` when raw landing is provisional.

## Expected Improvement

The instrument-reference policy is now explicit across the write and read lifecycle:

- persistence may land raw transaction evidence provisionally for ordering tolerance,
- product lifecycle processing blocks before cost, transaction-cost, lot-state, and processed-event
  publication when the instrument is missing,
- transaction-ledger and tax-lot source products degrade supportability for historical/orphan rows,
- the policy is reusable and testable instead of being an implied exception in the persistence
  consumer.

This keeps ingestion/persistence compatible while preventing downstream products from presenting
unresolved instrument references as fully governed lifecycle evidence.

## Tests Added

- Consumer test proving known instruments follow normal persistence and outbox publication.
- Consumer test proving missing instruments still allow raw landing but emit structured provisional
  policy evidence.
- Repository tests proving instrument master lookup SQL and blank-security skip behavior.

## Validation Evidence

Validation recorded before commit:

- `python -m pytest tests\unit\services\persistence_service\consumers\test_persistence_transaction_consumer.py tests\unit\services\persistence_service\repositories\test_transaction_db_repository.py -q --tb=short`
  passed with 8 tests.
- `python -m pytest tests\unit\services\persistence_service\consumers\test_persistence_transaction_consumer.py tests\unit\services\persistence_service\repositories\test_transaction_db_repository.py tests\unit\services\calculators\cost_calculator_service\consumer\test_cost_calculator_consumer.py -q --tb=short`
  passed with 42 tests.
- `python -m pytest tests\unit\services\query_service\services\test_transaction_metadata.py tests\unit\services\query_service\services\test_transaction_records.py tests\unit\services\query_service\services\test_transaction_service.py tests\unit\services\query_service\repositories\test_transaction_repository.py -q --tb=short`
  passed with 73 tests.
- `python -m pytest tests\unit\services\query_service\services\test_portfolio_tax_lot_window.py tests\unit\services\query_service\repositories\test_buy_state_repository.py -q --tb=short`
  passed with 26 tests.
- Scoped Ruff check passed for the persistence consumer, repository, policy, and tests.
- Scoped Ruff format check passed for the persistence consumer, repository, policy, and tests.
- `make typecheck` passed with no issues in 50 source files.
- `make openapi-gate` passed.
- `make api-vocabulary-gate` passed.
- `make quality-wiki-docs-gate` passed.
- `git diff --check` passed.
- Stranded-truth reconciliation found only active Dependabot branches for GitHub Actions and
  Python runtime dependency maintenance; neither contains unique durable #674 instrument-reference
  truth.
- `../lotus-platform/automation/Sync-RepoWikis.ps1 -CheckOnly -Repository lotus-core` failed
  because the published GitHub wiki is not synchronized with repo-authored wiki source. Current
  drift includes `Data-Models.md`, `Mesh-Data-Products.md`, `Operations-Runbook.md`, and
  `Outbox-Events.md`. Repo-local wiki source remains the authored truth and must be published after
  merge.

## Downstream Compatibility

No route path, request DTO, response DTO, Kafka topic, event payload, database schema, transaction
UPSERT behavior, outbox success payload, cost formula, lot-state field, or source-data response
field was removed.

The intentional additive behavior is a governed policy decision and source-safe warning when raw
transaction landing proceeds before instrument master data arrives. Lifecycle processing and
source-product supportability continue to enforce/degrade unresolved references through CR-1201,
CR-1203, and CR-1204.

## Documentation And Wiki Decision

- Updated the codebase review ledger.
- Updated `REPOSITORY-ENGINEERING-CONTEXT.md`.
- Updated `quality/quality_scorecard.md`.
- Updated `quality/refactor_health_report.md`.
- Updated repo-local `wiki/Data-Models.md` because the data-model orientation now needs to state
  the raw landing versus lifecycle/read-side supportability boundary.

## Remaining Follow-Up

- PR/CI/QA validation is still required before #674 can close.
- Post-merge wiki publication is required because repo-authored wiki source changed.
- A future stricter source-batch quarantine or database FK can be evaluated if platform ingestion
  ordering guarantees become strong enough to reject unresolved instruments at raw landing time.
