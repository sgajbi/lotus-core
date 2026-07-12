# CR-1202 Cashflow Consumer Unit-Of-Work Boundary

Date: 2026-06-30

## Scope

Cashflow-calculator transaction consumer processing for `transactions.persisted` events.

## Finding

GitHub issue #666 is valid. The cashflow consumer started one database transaction in
`_process_validated_cashflow_event(...)`, but branch helpers owned individual commit and rollback
decisions. That made durable behavior harder to audit because duplicate handling, stale replay
skips, epoch-fence rejection, non-cashflow lifecycle events, and successful cashflow calculation
could each finalize the unit of work from different helper branches.

That is a resilience and correctness risk because cashflow persistence and outbox staging must stay
atomic, and replay outcomes must remain deterministic under duplicate, stale, and fenced event
traffic.

## Action Taken

Added an explicit cashflow processing outcome policy:

1. branch helpers now return `CashflowProcessingOutcome` values instead of committing or rolling
   back directly;
2. `_finalize_cashflow_unit_of_work(...)` is the single application boundary that commits durable
   outcomes or rolls back rejected outcomes;
3. physical duplicate and epoch-fence rejection roll back the current claim attempt;
4. stale replay skip, semantic duplicate, non-cashflow lifecycle event, and successful calculation
   commit the durable idempotency or staged cashflow/outbox state;
5. cashflow persistence and outbox creation remain staged before the single commit boundary.

The reusable platform pattern is that consumers should classify the outcome first, then finalize
the unit of work once. Branch helpers can stage domain/application effects, but they should not own
transaction finalization.

## Compatibility

Downstream event contracts, cashflow rows, outbox payloads, duplicate handling, stale replay
semantics, epoch fencing, DLQ behavior, API contracts, and database schema are unchanged. The
intentional change is structural: transaction finalization is centralized and directly tested.

## Evidence

Focused behavior proof:

- `python -m pytest tests/unit/services/calculators/cashflow_calculator_service/unit/consumers/test_cashflow_transaction_consumer.py -q`
- Result: `24 passed`

Focused static proof:

- `python -m ruff check src/services/calculators/cashflow_calculator_service/app/consumers/transaction_consumer.py tests/unit/services/calculators/cashflow_calculator_service/unit/consumers/test_cashflow_transaction_consumer.py`
- Result: passed
- `python -m ruff format --check src/services/calculators/cashflow_calculator_service/app/consumers/transaction_consumer.py tests/unit/services/calculators/cashflow_calculator_service/unit/consumers/test_cashflow_transaction_consumer.py`
- Result: passed
- `make typecheck`
- Result: passed, no issues in 50 source files
- `make quality-wiki-docs-gate`
- Result: passed
- `git diff --check`
- Result: passed
- `../lotus-platform/automation/Sync-RepoWikis.ps1 -CheckOnly -Repository lotus-core`
- Result: failed because the published GitHub wiki is not synchronized with repo-authored wiki
  source. Reported drift: `Data-Models.md`, `Event-Replay-Service.md`,
  `Financial-Reconciliation.md`, `Ingestion-Service.md`, `Mesh-Data-Products.md`,
  `Operations-Runbook.md`, `Outbox-Events.md`, `Validation-and-CI.md`.

## Residual Risk

Issue #666 remains open for PR/CI/QA evidence until the branch is reviewed and merged. Follow-up
consumer refactors should apply the same classify-then-finalize unit-of-work pattern where helper
branches still own commit or rollback.

## Documentation And Wiki Decision

Repository-local architecture evidence and context are updated in this slice. No wiki source change
is needed because the change does not alter operator runbooks, externally supported APIs, or
client-facing behavior.

## Bank-Buyable Control Movement

This slice improves:

1. transaction-boundary auditability for cashflow consumer processing,
2. deterministic replay and duplicate finalization behavior,
3. atomicity evidence for cashflow persistence and outbox staging,
4. a reusable event-consumer unit-of-work pattern for future defect slices.

It does not claim full bank-buyable readiness for every `lotus-core` consumer.
