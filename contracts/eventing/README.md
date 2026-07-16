# Event Runtime Contracts

This folder contains machine-readable, source-owned contracts for Lotus Core event runtime
topology and ordering.

`kafka-topic-runtime-contract.v1.json` inventories every active Core topic, its producer key,
required ordering scope, consumer group, state owner, duplicate policy, replay behavior, governed
partition count, and bounded in-flight capacity.

The contract intentionally records current limitations. In particular, the event family does not
yet carry a source-owned tenant identity. Transaction reprocessing requests preserve their public
transaction-id API while resolving authoritative portfolio identity before Kafka publication.
