# CR-1488: Atomic Transaction Readiness Signal

Date: 2026-07-10
Issue: #468
Status: Hardened locally; downstream compatibility event retirement pending

## Objective

Remove the redundant cost-plus-cashflow event fan-in after cost, cashflow, position, idempotency,
and outbox writes moved into one atomic transaction-processing unit of work. Preserve existing
readiness topics and payload contracts while reducing runtime coordination, lag, and failure modes.

## Findings

1. `ProcessedTransactionPersisted` is staged in the same database transaction as every financial
   module effect and becomes visible only after that transaction commits.
2. The pipeline orchestrator still consumed `cashflows.calculated`, claimed a second idempotency
   key, and waited for both events before publishing readiness. Event order, consumer lag, or one
   unhealthy group could therefore delay an already-complete transaction.
3. Event ownership, full-stack test services, and test port profiles still named deleted calculator
   deployables. The integration lane either requested nonexistent Compose services or collided on
   the target's default host port.
4. Static DLQ wiring discovery did not resolve dependency-injected consumer factory defaults, so it
   could miss the two target consumers while continuing to certify legacy names.

## Change

- Made `ProcessedTransactionPersisted` the authoritative atomic transaction-completion input to
  `pipeline_orchestrator_service`.
- Removed the cashflow stage consumer, handler/UoW method, consumer group, and cashflow prerequisite
  from the domain decision and repository compare-and-set.
- Retained `cost_event_seen` and `cashflow_event_seen` columns and output fields for schema/payload
  compatibility. The authoritative event records both as true; no database migration is required.
- Preserved `transaction_processing.ready` and
  `portfolio_security_day.valuation.ready`, with readiness reason
  `atomic_transaction_processing_completed`.
- Kept `cashflows.calculated` publication as a compatibility fact but removed its active in-repo
  consumer. No cashflow calculation or durable cashflow state was removed.
- Updated the event supportability catalog to the unified runtime owner and marked unconsumed
  compatibility events dormant for in-repo runtime ownership.
- Extended event-runtime discovery to resolve injected consumer factory defaults and made target
  DLQ arguments explicit.
- Replaced legacy services and port variables in the full-stack test runtime with the unified worker.

## Compatibility And Impact

Public APIs, database schemas, financial calculations, compatibility topic names, event payload
models, and readiness output topics remain unchanged. The intentional internal behavior change is
that readiness follows one atomic completion fact rather than two independently delivered facts.
This removes one Kafka consumer group and one processed-event claim per cashflow event.

Consumers must not infer that `cashflows.calculated` publication alone means the complete combined
transaction committed. The authoritative in-repo completion fact is
`ProcessedTransactionPersisted` from `portfolio_transaction_processing_service`.

## Validation

- `162` focused unit/contract tests passed.
- `7` pipeline PostgreSQL integration tests passed in `72.24s` on an isolated dynamic-port stack.
- MyPy passed for `23` touched source files.
- Ruff lint/format, Vulture, architecture boundary, event runtime contract, runtime boundary,
  in-process modularity, and in-process boundary guards passed.
- Event ownership now resolves only active runtime catalog identities and DLQ discovery includes
  `TransactionProcessingConsumer` and `BookedTransactionReplayRequestConsumer`.
- Repo-native wiki validation passed. Platform `Sync-RepoWikis.ps1 -CheckOnly` reports expected
  feature-branch drift; publish the repo-authored wiki only after merge to `main`.

## Remaining Work

Retain `transactions.cost.processed`, `cashflows.calculated`, and
`transaction_processing.ready` until downstream usage and retention evidence permit contract
retirement. Archive or migrate historical transaction-stage rows only after support requirements
are agreed. Complete shutdown-under-load, database pool/latency evidence, registry publication,
controlled cluster rollout, and canonical platform QA under #468.
