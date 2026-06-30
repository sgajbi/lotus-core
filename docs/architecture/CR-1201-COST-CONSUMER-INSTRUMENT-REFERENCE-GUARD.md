# CR-1201 Cost Consumer Instrument Reference Guard

Date: 2026-06-30

## Scope

Cost-calculator transaction processing and BUY lot-state persistence.

## Finding

GitHub issue #674 is valid. Transactions and lot-state rows carry `instrument_id` and
`security_id` as strings while instrument master data lives in `instruments`. The cost consumer
already loaded instrument metadata when available, but product transactions could continue through
cost and lot-state persistence when that master row was missing.

That could create normal-looking calculated cost, fee, and lot-state evidence for unresolved or
mistyped instruments, weakening downstream valuation, tax-lot, performance-economics, and advisory
source-product supportability.

## Action Taken

Added an explicit cost-consumer reference-integrity guard:

1. product transaction processing now requires an instrument master row before cost-engine
   processing, transaction-cost persistence, BUY lot-state persistence, or processed-event
   publication;
2. missing instrument references raise `InstrumentReferenceUnavailableError`;
3. the consumer maps the error to `RetryableConsumerError`, so the message is deferred without DLQ
   or offset-commit semantics while upstream instrument master data can arrive;
4. existing FX contract and pure adjustment paths remain exempt because they have specialized
   instrument-creation or cash-leg validation flows.

The guard is intentionally application-level rather than a database foreign key in this slice. That
preserves ingestion ordering flexibility while making unresolved product-instrument references
explicit and testable instead of silently normal.

## Compatibility

Known-instrument transaction behavior is preserved. The intentional behavior change is that product
transactions with missing instrument master data no longer update costs, write BUY lot state, emit
processed outbox events, or DLQ immediately; they defer as retryable reference-data dependencies.

## Evidence

Focused behavior proof:

- `python -m pytest tests/unit/services/calculators/cost_calculator_service/consumer/test_cost_calculator_consumer.py -q`
- Result: `34 passed`

Focused static proof:

- `python -m ruff check src/services/calculators/cost_calculator_service/app/consumer.py tests/unit/services/calculators/cost_calculator_service/consumer/test_cost_calculator_consumer.py`
- Result: passed
- `python -m ruff format --check src/services/calculators/cost_calculator_service/app/consumer.py tests/unit/services/calculators/cost_calculator_service/consumer/test_cost_calculator_consumer.py`
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

This is the first write-side enforcement slice for issue #674. Follow-up work should add broader
ingestion-side policy and read-side degraded supportability for historical rows that predate this
guard or entered through other write paths.

Issue #674 remains open for PR/CI/QA evidence and broader completion.

## Bank-Buyable Control Movement

This slice improves:

1. instrument reference integrity for cost and lot-state lifecycle writes,
2. deterministic retry behavior for out-of-order instrument/transaction ingestion,
3. prevention of normal-looking downstream cost/lot evidence for unresolved instruments,
4. a reusable reference-data dependency pattern aligned with #673 cash-account provenance.

It does not claim full closure of every instrument-reference path in `lotus-core`.
