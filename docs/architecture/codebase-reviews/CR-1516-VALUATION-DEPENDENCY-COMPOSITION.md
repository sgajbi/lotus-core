# CR-1516: Valuation Dependency Composition

Date: 2026-07-11
Issue: #468 same-pattern architecture scan
Status: Implemented locally; valuation application/domain extraction pending

## Objective

Remove concrete database session and repository/idempotency/outbox construction from the position
valuation processor without falsely moving the persistence-model workflow into an application
package.

## Finding

`ValuationJobProcessor` mixed reusable valuation sequencing with a default database session provider
and a concrete dependency factory. Tests patched those constructors inside the processor module.
The processor still creates persistence snapshots, records metrics, and owns concrete transaction
handling, so a folder-only move to `application` would misrepresent the architecture.

## Implementation

- Made the session provider and dependency factory mandatory processor dependencies.
- Moved production defaults and concrete repository/idempotency/outbox construction to
  `app/infrastructure` composition.
- Changed the consumer to use the infrastructure builder while retaining explicit processor
  injection for tests and alternate entry points.
- Replaced constructor patching with fixed dependency-factory/session-provider fixtures.
- Added structural proof that the processor cannot construct those infrastructure dependencies.
- Added responsibility docstrings, slotted immutable dependency/result records, explicit `None`
  resolution, and removed the redundant session wrapper.

## Boundary Decision

`position_valuation_calculator` remains independently deployable because valuation is job and
market-data driven with a different compute, backfill, failure, and scaling profile from booked
transaction processing. `ValuationJobProcessor` remains transitional at the service root until
framework-neutral valuation records, repository/publication ports, metrics observation, and a unit
of work are extracted. No new runtime or database boundary was added.

## Compatibility

No calculation, valuation status, Kafka topic/payload, idempotency service name, outbox event,
database schema, transaction behavior, retry/DLQ classification, metric, API, or downstream
contract changed.

## Validation

- Position valuation unit cohort: `56 passed`.
- Real PostgreSQL persistence/idempotency/outbox/ownership cohort: `3 passed in 69.40s`.
- Position valuation image built from the corrected wheel; installed `app.main`, composition, and
  processor imports passed.
- Image inspection exposed all required local provenance labels.
- Ruff, formatting, targeted MyPy, testability, infrastructure-layer, and diff guards passed.
- Reconciliation onto the post-PR-727 mainline reran the focused unit, MyPy, Ruff, architecture,
  documentation, and diff checks; installed-image proof remains part of the aggregate release gate.

## Follow-Up

Define framework-neutral valuation input/result records, repository and snapshot-publication ports,
an observability port, and a transaction unit-of-work boundary before moving the processor under
`application`. Keep valuation separate from transaction processing unless representative workload
and failure evidence disproves its current isolation value.
