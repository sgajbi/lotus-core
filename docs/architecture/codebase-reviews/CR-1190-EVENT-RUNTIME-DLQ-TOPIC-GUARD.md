# CR-1190 Event Runtime DLQ Topic Guard

Date: 2026-06-30

## Objective

Fix GitHub issue #671 by making RFC-0083 runtime event contract governance validate DLQ topic
wiring on `BaseConsumer`-backed workers.

## Change

- `scripts/event_runtime_contract_guard.py` now discovers classes that inherit from
  `BaseConsumer`, including indirect subclasses, and validates `dlq_topic=` constructor wiring.
- The guard resolves literal DLQ topics, `portfolio_common.config` constants, and local aliases such
  as `dlq_topic = KAFKA_PERSISTENCE_SERVICE_DLQ_TOPIC`.
- The guard fails when a `BaseConsumer` DLQ topic is unresolved or not present in the governed
  RFC-0083 direct Kafka topic catalog.
- `dlq.persistence_service` is now represented as `PersistenceServiceDlq` in the governed direct
  Kafka topic catalog with a BaseConsumer DLQ payload contract, correlation/idempotency header
  expectations, replay consumers, and ingestion evidence linkage.

## Expected Improvement

CI now covers the runtime DLQ publication path that was previously hidden behind `self.dlq_topic`.
Consumer-manager drift to an uncataloged or dynamic DLQ topic becomes a deterministic guard failure
instead of silently weakening incident replay, auditability, and failure triage.

## Tests Added

- Current runtime discovery proves configured `BaseConsumer` DLQ wiring includes
  `dlq.persistence_service`.
- Temporary-source AST tests prove literal, config-constant, local-alias, indirect-subclass, and
  dynamic DLQ topic handling.
- Contract evaluation tests prove uncataloged and unresolved DLQ topics fail with explicit
  diagnostics.
- Contract evaluation tests prove cataloged literal and config-backed DLQ topics pass.

## Validation Evidence

- `python -m pytest tests/unit/scripts/test_event_runtime_contract_guard.py -q` passed with 14 tests.
- `python scripts/event_runtime_contract_guard.py` passed.
- `python -m ruff check scripts/event_runtime_contract_guard.py src/libs/portfolio-common/portfolio_common/event_supportability.py tests/unit/scripts/test_event_runtime_contract_guard.py`
  passed.
- `python -m ruff format --check scripts/event_runtime_contract_guard.py src/libs/portfolio-common/portfolio_common/event_supportability.py tests/unit/scripts/test_event_runtime_contract_guard.py`
  passed.
- `git diff --check` passed.

## Downstream Compatibility

No API route, DTO, Kafka topic name, database schema, DLQ payload field, consumer group, or runtime
publish behavior changed. The behavior change is limited to CI/governance: miswired or uncataloged
DLQ topics now fail the runtime contract guard.

## Documentation And Wiki Decision

This architecture record, the codebase review ledger, and quality/refactor scorecards were updated.
No wiki update is required because no operator-facing command, runbook, or published API contract
changed.

## Remaining Follow-Up

- Add broader DLQ topic catalog entries if additional service-specific DLQs are introduced.
- Consider a separate DLQ catalog only if DLQ payload contracts diverge from direct Kafka topic
  supportability enough to need distinct validation fields.
- Let GitHub CI prove the guard in the repository quality lane before closing issue #671.
