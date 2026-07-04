# CR-1321 Transaction Replay Boundary

## Scope

Issue cluster: GitHub issue #628.

This slice splits transaction replay planning and error classification from SQLAlchemy and Kafka
runtime adapters.

## Objective

Make transaction replay ordering, deduplication, event planning, explicit correlation metadata,
partial publish failure classification, and flush-timeout classification unit-testable without an
`AsyncSession`, Kafka producer, or global correlation context.

## Changes

1. Added `portfolio_common.reprocessing_replay` with transaction replay reader and publisher
   ports, `ReplayCorrelationMetadata`, replay message/plan models, ordered-id deduplication,
   event planning, and publish/flush error classification.
2. Refactored `ReprocessingRepository` into a compatibility composition adapter that preserves the
   existing constructor and `reprocess_transactions_by_ids(...)` public method.
3. Added `SqlAlchemyTransactionReplayReader` for SQL query construction.
4. Added `KafkaTransactionReplayPublisher` for Kafka publish and flush behavior.
5. Added `ReprocessingRepository.from_ports(...)` for fake-port orchestration tests.
6. Added pure replay tests for ordering, explicit headers, event payload planning, partial publish
   failure, and flush timeout without database or Kafka.
7. Added `scripts/transaction_replay_boundary_guard.py` and wired it into
   `make architecture-guard`.
8. Added `docs/standards/transaction-replay-boundary-standard.md`.

## Behavior And Compatibility

No public repository constructor, caller contract, Kafka topic, Kafka key, payload field, SQL
filter, SQL ordering intent, flush behavior, error message, failure payload field, consumer
contract, API route, database schema, or runtime topology changed.

`ReprocessingReplayError` remains importable from
`portfolio_common.reprocessing_repository` for compatibility.

## Validation Evidence

Focused local validation:

1. `python -m pytest tests/unit/libs/portfolio-common/test_reprocessing_replay.py tests/unit/libs/portfolio-common/test_reprocessing_repository.py tests/unit/scripts/test_transaction_replay_boundary_guard.py tests/unit/services/calculators/cost_calculator_service/consumer/test_reprocessing_consumer.py tests/unit/tools/test_reprocess_transactions.py -q`
2. `python scripts/transaction_replay_boundary_guard.py`
3. `python -m ruff check <touched Python paths>`
4. `python -m ruff format --check <touched Python paths>`

Aggregate validation before commit:

1. `make architecture-guard`
2. `python scripts/wiki_validation_guard.py`
3. `git diff --check`

All listed commands passed locally before commit.

## Documentation, Wiki, Context, And Skill Decision

Updated repo-local standards, architecture overview, codebase review ledger, and repo context.

No wiki update is required because this slice changes internal component ownership and does not
change operator-facing commands, public API behavior, supported features, or published wiki truth.

No platform skill source change is required in this slice because the existing backend delivery
guidance already directs concrete database/Kafka coupling toward ports, adapters, fake-port tests,
guards, and repo context.

## Remaining Work

GitHub issue #628 is locally fixed for the pure replay planner, reader/publisher ports, explicit
correlation metadata, fake-port unit tests, and adapter-preserving compatibility pending PR CI/QA
and issue closure.

Broader replay workflow consolidation in event-replay APIs remains separate issue scope.
