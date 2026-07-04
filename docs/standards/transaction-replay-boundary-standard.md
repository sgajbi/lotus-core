# Transaction Replay Boundary Standard

Transaction replay must be split across replay planning, read access, and publication adapters.

## Responsibilities

`portfolio_common.reprocessing_replay` owns:

1. ordered transaction-id deduplication,
2. explicit replay correlation metadata and header construction,
3. transaction replay event payload planning,
4. replay message construction,
5. partial publish failure classification,
6. flush timeout classification.

`portfolio_common.reprocessing_repository` owns compatibility composition for the existing
`ReprocessingRepository` public API:

1. `SqlAlchemyTransactionReplayReader` keeps SQL query construction behind the reader port,
2. `KafkaTransactionReplayPublisher` keeps Kafka publish and flush behavior behind the publisher
   port,
3. `ReprocessingRepository.from_ports(...)` allows pure port tests without database or Kafka
   collaborators.

## Boundary Rules

The pure replay module must not import SQLAlchemy sessions, Kafka producers, or global correlation
context. Correlation metadata is passed explicitly as `ReplayCorrelationMetadata`.

The compatibility repository must not rebuild transaction event payloads, duplicate ordered-id
deduplication, or reconstruct correlation headers locally.

## Enforcement

`make architecture-guard` runs `scripts/transaction_replay_boundary_guard.py`.

## Compatibility

This is an in-process design modularity rule. It preserves the existing
`ReprocessingRepository(db, kafka_producer).reprocess_transactions_by_ids(...)` contract and does
not change Kafka topics, payload shape, SQL filters, flush behavior, error messages, or runtime
topology.
