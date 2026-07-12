# CR-1495: Canonical Replay Derived-State Repair

Date: 2026-07-12
Issues: #468, PR #725 review
Status: Hardened locally; PR and mainline validation pending

## Objective

Allow an authorized canonical booked-transaction replay to repair missing or stale derived cost,
cashflow, position, and readiness state without weakening ordinary semantic duplicate suppression.

## Finding

Semantic transaction identity correctly stopped an identical payload delivered at a new Kafka
offset. The canonical replay publisher used that same delivery path, so an acknowledged replay of
an already-claimed transaction returned `DUPLICATE` before any financial module ran. It could not
repair derived state even though replay publication succeeded.

## Design

- Canonical replay publications carry the internal delivery header
  `lotus-transaction-processing-intent=repair`. The business `TransactionEvent` remains unchanged.
- The Kafka mapper accepts only the exact single repair value. Missing headers remain standard
  processing; duplicate or unknown values fail closed.
- A standard semantic duplicate remains a no-op. A semantic conflict remains terminal and cannot
  be bypassed by repair intent.
- A repair semantic duplicate claims a separate physical delivery fence in the same SQLAlchemy
  unit of work before financial processing. Redelivery of the same Kafka offset remains a no-op,
  while rollback releases the repair claim for retry.
- Cashflow repair bypasses only the already-proven semantic cashflow fence, retains epoch fencing,
  and restores the canonical transaction/epoch row with one PostgreSQL conflict-update statement
  keyed by `_transaction_epoch_uc`. Existing rows are replaced from recalculated values and
  concurrent missing-row repairs converge without a check-then-insert race.
- Cashflow create and repair repositories return an immutable `StoredCashflow` record. The new
  path does not expose SQLAlchemy rows, and the prior `create_cashflow` transitional output-shape
  exception is removed.
- Runtime load proof treats canonical replay as completed repair work: its drain probe waits for
  incremental `transaction/processed` outcomes. Ordinary duplicate-delivery proof continues to
  use `transaction/duplicate`; the two operational intents are not conflated.

The Kafka topic ACL and the governed reprocessing ingress remain the authorization boundary for
the internal repair marker. The marker is not accepted from an API DTO or transaction payload.

## Compatibility

No public route, OpenAPI schema, transaction event payload, database schema, topic name, consumer
group, or ordinary duplicate behavior changes. Canonical replay delivery gains one internal header
and intentionally changes from an acknowledged no-op to one fenced repair execution when the
semantic transaction already exists.

## Validation

- `210` replay, transaction-processing, cashflow, and output-shape unit tests passed.
- `3` PostgreSQL replay scenarios passed, including missing cashflow/position restoration and
  replacement of a corrupted existing cashflow.
- A two-session PostgreSQL scenario proved concurrent missing-row repairs converge on one row.
- The complete transaction-processing contract passed `37` scenarios.
- Focused MyPy and Ruff checks passed.
- Transaction replay, event runtime, repository output-shape, strict architecture, domain,
  application, port, adapter, repository-transaction, image-provenance, and documentation catalog
  guards passed.
- The performance-gate regression cohort passed `7` tests and now asserts the repair-replay
  completion metric explicitly. Full fast-tier runtime evidence is pending the corrected PR gate.

## Durable Guidance Decision

Repository context and the transaction-processing consolidation ledger are updated because the
repair-versus-duplicate rule is Core-specific runtime truth. No OpenAPI, migration, wiki, or
platform skill change is required. The existing backend delivery skill already requires replay
idempotency, typed recovery intent, real-database proof, and fail-closed recovery controls.
